"""never-report-confidence-on-an-empty-answer, return-the-fetched-body-on-empty-extraction.

Source: `docs/findings/2026-08-07-a2web-call-trace-audit.md` §4c, deterministic
over 2,856 real calls (not model-judged). 42 calls shipped `status: failed` AND
`confidence: high` AND `answer: ""`; 35 carried `operator_hints: [extraction_empty]`
reading "Fetched N characters but extraction produced an EMPTY answer", median
N=8,788, max 78,623.

**Why `test_obstacle_confidence_guard.py`'s existing cap does not cover this.**
That file caps confidence off `routing.obstacle` — the extractor's OWN
self-report, produced only when extraction ran far enough to build a
`RouterPayload` at all. An empty answer has two other causes that never get
that far: a provider error (`_ErroringProvider`, see `test_fetcher_ask.py`) and
no LLM backend configured. Both leave `routing = None`, so `obstacle` is
`None`, the existing cap's `if obstacle in _CONFIDENCE_CAPPING_OBSTACLES` never
fires, and `_confidence_for`'s length-only estimate — `high` whenever the fetched
body exceeds 2000 chars, which the audit's own median (8,788) clears easily —
ships unchallenged over an answer that does not exist.

`fr.ask_unanswered` is the fix: a fact carried from `build_response`, where the
three causes (parse-empty, provider error, no backend) are already unified
under one `ask_unanswered` local (`never-silently-miss-at-extraction-granularity`).
Reading it here means the cap applies regardless of which of the three caused it,
without re-deriving the union from three different FetchResponse fields.
"""

from __future__ import annotations

from a2web.fetcher_response import build_ask_response
from a2web.models import Confidence, FetchResponse, FetchStatus


def _fr_unanswered(*, ask_unanswered: bool, confidence: Confidence = Confidence.high, content_md: str = "x" * 8788) -> FetchResponse:
    """A fetch that succeeded (verdict ok, real body) but produced no answer.

    `routing=None` on purpose — this is the provider-error / no-backend shape,
    where extraction never got far enough to build a `RouterPayload`. If the
    fix regressed to reading `obstacle` instead of `ask_unanswered`, this
    fixture would prove it: there is no obstacle here to cap on.
    """
    return FetchResponse(
        url="https://hepsiburada.com/some-product-p123",
        status=FetchStatus.failed,
        tier="raw",
        confidence=confidence,
        extracted_answer="",
        routing=None,
        content_md=content_md,
        ask_unanswered=ask_unanswered,
    )


def test_empty_answer_with_no_obstacle_signal_is_still_capped_to_low() -> None:
    """The mutation this guards: `obstacle` is None, so the OLD cap does nothing."""
    ask = build_ask_response(_fr_unanswered(ask_unanswered=True), include_content=False, debug=False)
    assert ask.confidence == Confidence.low, (
        "an empty answer shipped a non-low confidence with no `obstacle` to cap it on. "
        "This is the exact shape of the 2026-08-07 audit's 42 calls: status=failed, "
        "answer='', confidence=high."
    )


def test_a_healthy_answer_is_unaffected() -> None:
    """The cap must be scoped to `ask_unanswered`, not become a blanket downgrade."""
    fr = _fr_unanswered(ask_unanswered=False, confidence=Confidence.high)
    fr.extracted_answer = "A real, substantive answer."
    fr.status = FetchStatus.ok
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.confidence == Confidence.high


def test_the_fetched_body_is_attached_when_extraction_came_back_empty() -> None:
    """The other half of the audit finding: don't discard a body already in hand.

    `include_content=False` is the default — the caller did not ask for the
    full page — but that default must not also mean "and the answer is empty,
    so here is nothing at all". `content_md` is forced onto the wire despite
    the default (a2web-brn — previously a separate `thin_content` fallback
    field; merged since both carried the identical body).
    """
    body = "x" * 8788
    ask = build_ask_response(_fr_unanswered(ask_unanswered=True, content_md=body), include_content=False, debug=False)
    assert ask.content_md == body, "a successfully fetched body was discarded on an empty extraction"


def test_the_body_is_not_duplicated_when_the_caller_already_opted_in() -> None:
    """Forcing the body when `ask_unanswered` and opting in via `include_content=True`
    both resolve to the same single `content_md` — never two copies under two keys."""
    body = "x" * 8788
    ask = build_ask_response(_fr_unanswered(ask_unanswered=True, content_md=body), include_content=True, debug=False)
    assert ask.content_md == body


def test_a_healthy_answer_gets_no_forced_content() -> None:
    fr = _fr_unanswered(ask_unanswered=False)
    fr.extracted_answer = "A real answer."
    fr.status = FetchStatus.ok
    ask = build_ask_response(fr, include_content=False, debug=False)
    assert ask.content_md == ""
