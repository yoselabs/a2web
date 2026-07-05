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
