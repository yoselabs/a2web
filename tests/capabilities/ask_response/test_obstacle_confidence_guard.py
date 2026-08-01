"""Confabulation guard — the extractor's obstacle signal caps ask confidence.

search-retrieval-and-confabulation-guard P2: `build_ask_response` reconciles
the LLM's `obstacle` field with `confidence` / `retrieval_incomplete`, so a
fluent-but-unfounded answer (SPA shell / stale page) can no longer surface as
`confidence: high`. The reconciliation lives at the ask projection because
`obstacle` is produced after `build_response`.
"""

from __future__ import annotations

from a2web.fetcher_response import build_ask_response
from a2web.models import (
    Confidence,
    FetchResponse,
    FetchStatus,
    Obstacle,
    RouterPayload,
)


def _fr(*, obstacle: Obstacle | None, confidence: Confidence = Confidence.high) -> FetchResponse:
    """An otherwise-healthy ok ask response with a router payload carrying `obstacle`."""
    routing = RouterPayload(
        answer="A fluent answer that reads plausible.",
        structural_form="article",
        shape="prose",
        obstacle=obstacle,
    )
    return FetchResponse(
        url="https://hn.algolia.com/?q=claude",
        status=FetchStatus.ok,
        tier="browser",
        confidence=confidence,
        extracted_answer="A fluent answer that reads plausible.",
        routing=routing,
    )


def _hint_codes(ask: object) -> list[str]:
    return [h.code for h in ask.operator_hints]  # type: ignore[attr-defined]


def test_empty_obstacle_caps_high_confidence_to_low() -> None:
    ask = build_ask_response(_fr(obstacle="empty"), include_content=False, debug=False)
    assert ask.confidence == Confidence.low


def test_blocked_obstacle_caps_confidence() -> None:
    ask = build_ask_response(_fr(obstacle="blocked"), include_content=False, debug=False)
    assert ask.confidence == Confidence.low


def test_paywalled_and_error_cap_confidence() -> None:
    for obstacle in ("paywalled", "error"):
        ask = build_ask_response(_fr(obstacle=obstacle), include_content=False, debug=False)  # type: ignore[arg-type]
        assert ask.confidence == Confidence.low


def test_healthy_page_keeps_computed_confidence() -> None:
    ask = build_ask_response(_fr(obstacle=None, confidence=Confidence.high), include_content=False, debug=False)
    assert ask.confidence == Confidence.high


def test_downgrade_only_never_raises() -> None:
    """A low base confidence with an obstacle stays low (never bumped up)."""
    ask = build_ask_response(_fr(obstacle="empty", confidence=Confidence.low), include_content=False, debug=False)
    assert ask.confidence == Confidence.low


# --------------------------------------------------------------------- #
# retrieval-incompleteness
# --------------------------------------------------------------------- #


def test_empty_obstacle_flags_retrieval_incomplete_with_hint() -> None:
    ask = build_ask_response(_fr(obstacle="empty"), include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert "retrieval_incomplete" in _hint_codes(ask)


def test_blocked_obstacle_flags_retrieval_incomplete() -> None:
    ask = build_ask_response(_fr(obstacle="blocked"), include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert "retrieval_incomplete" in _hint_codes(ask)


def test_paywalled_error_do_not_force_incomplete_here() -> None:
    for obstacle in ("paywalled", "error"):
        ask = build_ask_response(_fr(obstacle=obstacle), include_content=False, debug=False)  # type: ignore[arg-type]
        assert ask.retrieval_incomplete is False
        assert "retrieval_incomplete" not in _hint_codes(ask)


def test_healthy_page_not_flagged() -> None:
    ask = build_ask_response(_fr(obstacle=None), include_content=False, debug=False)
    assert ask.retrieval_incomplete is False
    assert "retrieval_incomplete" not in _hint_codes(ask)


# --------------------------------------------------------------------- #
# structured-grounded carve-out (structured-grounded-completeness)
# --------------------------------------------------------------------- #


def _fr_grounded(*, obstacle: Obstacle | None, answer: str, structured_grounded: bool) -> FetchResponse:
    """An ok ask response from a (maybe) structured-exemption-promoted page."""
    routing = RouterPayload(answer=answer, structural_form="product", shape="key-value", obstacle=obstacle)
    return FetchResponse(
        url="https://www.veito.com/iletisim-EN.html",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.medium,  # promoted-thin page: verdict ok, short content
        extracted_answer=answer,
        routing=routing,
        structured_grounded=structured_grounded,
    )


def test_structured_grounded_empty_obstacle_not_flagged() -> None:
    """Thin structured page, non-empty answer, obstacle=empty → NOT incomplete,
    no critical hint, but confidence stays low (the honest hedge)."""
    fr = _fr_grounded(obstacle="empty", answer="Phone 444 3 061, email destek@veito.com", structured_grounded=True)
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.retrieval_incomplete is False
    assert "retrieval_incomplete" not in _hint_codes(ask)
    assert ask.confidence == Confidence.low


def test_structured_grounded_blocked_still_flagged() -> None:
    """The carve-out is empty-only: a blocked obstacle still flags incomplete."""
    fr = _fr_grounded(obstacle="blocked", answer="Some answer", structured_grounded=True)
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert "retrieval_incomplete" in _hint_codes(ask)


def test_structured_grounded_empty_answer_still_flagged() -> None:
    """An EMPTY answer is out of scope — the carve-out requires a non-empty answer."""
    fr = _fr_grounded(obstacle="empty", answer="", structured_grounded=True)
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert "retrieval_incomplete" in _hint_codes(ask)


def test_non_grounded_empty_obstacle_still_flagged() -> None:
    """Without the structured_grounded signal, empty obstacle flags as before."""
    fr = _fr_grounded(obstacle="empty", answer="A fluent answer", structured_grounded=False)
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert "retrieval_incomplete" in _hint_codes(ask)


def test_phase_two_never_clears_phase_one_incompleteness() -> None:
    """The COMPREHENSION phase is set-only — it cannot talk a2web out of a miss.

    `retrieval_incomplete` is decided in two named phases (see the note above
    `_CONFIDENCE_CAPPING_OBSTACLES`): the RETRIEVAL phase in `build_response`,
    from the verdict and the carried terminal classification, and the
    COMPREHENSION phase here, from the extractor's `obstacle`.

    Phase 2 must only ever RAISE the flag. If it could lower it, an extractor
    that failed to notice a wall — or one that read a rendered challenge page as
    ordinary prose, which is exactly what an SPA shell looks like — would
    override a miss the ladder had already proved, and the caller would receive
    a confident silent miss. That is the ADR-0009 harm, arrived at from the one
    direction the fetch machinery cannot see.

    Swept across every obstacle value INCLUDING the two carve-outs
    (`structured_grounded_empty`, `small_page_answered`), which suppress phase 2
    from raising the flag on a known false positive and must not be readable as
    licence to clear it.
    """
    obstacles: list[Obstacle | None] = [None, "empty", "blocked", "paywalled", "error"]
    for obstacle in obstacles:
        for grounded, small in ((False, False), (True, False), (False, True)):
            fr = _fr(obstacle=obstacle)
            fr.retrieval_incomplete = True
            fr.structured_grounded = grounded
            fr.small_page_confirmed = small

            ask = build_ask_response(fr, include_content=False, debug=False)

            assert ask.retrieval_incomplete, (
                f"phase 2 cleared phase 1's incompleteness (obstacle={obstacle!r}, "
                f"structured_grounded={grounded}, small_page_confirmed={small}). "
                "The comprehension phase is set-only: it may raise the flag, never lower it."
            )
