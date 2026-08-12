"""ADR-0020 (grounded absence): a gated section blocking the answer caps
confidence and is flagged — never `retrieval_incomplete`, never `low`.

Mirrors `test_failed_browser_rung_caps_confidence.py`'s shape: `fc` carries the
already-RESOLVED fact (`blocked_gated_section`), and `build_response` is
exercised directly rather than through the LLM seam — the resolution mechanism
itself (handle -> `GatedSection`, closed-set) is covered separately in
`test_gated_sections_detector.py` and `test_resolve_blocked_gate.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.verdict.terminal import _apply_terminal
from a2web.fetcher_response import build_response
from a2web.gated_sections import GatedSection
from a2web.hints import has_hint
from a2web.models import Confidence, FetchStatus, Verdict

_LONG_BODY = "x" * 2500  # clears _confidence_for's high threshold on its own

_QA_GATE = GatedSection(handle=1, label="Soru Cevap", stated_count=4)


def _fc(*, content_md: str, blocked_gated_section: GatedSection | None) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
            requested_url="https://www.hepsiburada.com/carraro-gravel-g2",
            ask="seller Q&A questions and answers full text",
        ),
        resources=FetchResources(sqlite=None),
        url="https://www.hepsiburada.com/carraro-gravel-g2",
        final_url="https://www.hepsiburada.com/carraro-gravel-g2",
        content_md=content_md,
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    fc.blocked_gated_section = blocked_gated_section
    _apply_terminal(fc)
    return fc


@pytest.mark.protects("change:flag-interaction-gated-sections")
def test_blocking_gate_caps_high_confidence_to_medium() -> None:
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=_QA_GATE)
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium, "a blocking gate shipped high confidence unchallenged"


@pytest.mark.protects("change:flag-interaction-gated-sections")
def test_blocking_gate_never_drops_to_low() -> None:
    """`low` is reserved for a non-ok verdict / page obstacle / no answer — states
    where retry is the right move. A gate is none of those; `low` would make it
    indistinguishable from `ask_unanswered`, contradicting the hint's own claim
    that re-querying is futile."""
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=_QA_GATE)
    fr = build_response(fc)
    assert fr.confidence != Confidence.low


@pytest.mark.protects("change:flag-interaction-gated-sections")
def test_blocking_gate_emits_interaction_required_hint() -> None:
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=_QA_GATE)
    fr = build_response(fc)
    assert has_hint(fr.operator_hints, "interaction_required")
    hint = next(h for h in fr.operator_hints if h.code == "interaction_required")
    assert "Soru Cevap" in hint.message
    assert "4" in hint.message
    assert hint.severity == "warning"


@pytest.mark.protects("change:flag-interaction-gated-sections")
def test_blocking_gate_does_not_fail_the_fetch() -> None:
    """Structurally unavailable: `retrieval_incomplete` is contractually bound
    to `status: failed` (ADR-0009), and the page retrieved fine."""
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=_QA_GATE)
    fr = build_response(fc)
    assert fr.retrieval_incomplete is False
    assert fr.status == FetchStatus.ok


@pytest.mark.protects("change:flag-interaction-gated-sections")
def test_no_blocking_gate_leaves_the_envelope_untouched() -> None:
    """The common case: no detected gate blocks the question — the by-far
    majority of fetches, including every one with NO gated sections at all."""
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=None)
    fr = build_response(fc)
    assert fr.confidence == Confidence.high
    assert not has_hint(fr.operator_hints, "interaction_required")
    assert fr.retrieval_incomplete is False


def test_blocking_gate_never_raises_an_already_low_confidence() -> None:
    """The cap is downgrade-only: a short body's already-medium confidence is untouched."""
    fc = _fc(content_md="short body under the high-confidence length floor", blocked_gated_section=_QA_GATE)
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium


def test_a_gate_with_no_stated_count_still_names_the_section() -> None:
    gate = GatedSection(handle=1, label="Hepsitaksit", stated_count=None)
    fc = _fc(content_md=_LONG_BODY, blocked_gated_section=gate)
    fr = build_response(fc)
    hint = next(h for h in fr.operator_hints if h.code == "interaction_required")
    assert "Hepsitaksit" in hint.message
