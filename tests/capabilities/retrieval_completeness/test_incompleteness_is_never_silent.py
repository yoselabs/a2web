"""Incompleteness may never be declared without a hint — swept, not sampled.

**The gap this closes, and why it needed a sweep to find.** ADR-0009 requires
that a caller cannot mistake a miss for an answer, and the operator hint is the
channel carrying the *remedy* — the one an agent acts on. Nothing guaranteed a
hint accompanied `retrieval_incomplete`, and the reason is structural rather
than a single bug:

  - `build_response`'s `render_requested` clause marks a stopped-ladder render
    incomplete "regardless of the handler's placeholder verdict" — it never
    consults the terminal classification.
  - `_apply_terminal` deliberately emits NO hint for `unreachable` or
    `operator_error` ("dns/content_type_mismatch are honestly terminal").

Whether those two ever meet is a reachability question spanning the whole tier
ladder. No single test could answer it, and no reviewer reading either site
would see the other. What a sweep CAN do is assert the two can never produce a
silent envelope, whatever the ladder does.

**Why this is a different instrument from its neighbours.** `test_classify_
terminal.py` and `test_terminal_is_carried_not_rederived.py` assert the
classifier's rules; most of them do it by re-encoding the rule in the test,
which cannot catch a rule that is wrong in both places. This asserts an
end-to-end PROPERTY of the composed result — terminal phase then response
builder, every verdict — and names no rule at all. It stays true through any
reclassification.

**On the shared implementation.** The check is `llm_eval.contract`'s, not a
local copy. A second implementation would drift from the one the bench and the
replay corpora use, and then "coherent" would mean two things.

Historical note on the sweep's own fallibility, kept because it is the lesson:
a first pass reported 172 of 172 combinations incoherent. That was the probe,
not the product — it built a `FetchContext` directly and never ran
`_apply_terminal`, so of course no hints existed. A second pass reported 4 of
26; two of those were still the probe (`paid_auth_error` emits its hint at the
paid tier, which a synthetic context does not run). An exhaustive sweep is only
as sound as the pipeline stages it actually executes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext
from a2web.fetcher.verdict.terminal import _apply_terminal
from a2web.fetcher_response import build_response
from a2web.llm_eval.contract import _check_incompleteness_coherence
from a2web.models import Verdict


def _envelope(*, verdict: Verdict, render_requested: bool) -> dict[str, object]:
    """Drive the real terminal phase and the real response builder.

    `_apply_terminal` is not optional decoration — it is the pipeline stage
    that attaches the hint, so a probe omitting it measures its own omission.
    """
    fc = FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="x",
        sqlite=None,
        bypass_cache=True,
        url="https://e.com/p",
        final_url="https://e.com/p",
        render_requested=render_requested,
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=verdict)
    _apply_terminal(fc)
    fr = build_response(fc)
    return {
        "status": getattr(fr.status, "value", fr.status),
        "retrieval_incomplete": fr.retrieval_incomplete,
        "narrative": fr.narrative,
        "operator_hints": [h.code for h in fr.operator_hints],
    }


@pytest.mark.parametrize("render_requested", [True, False], ids=["render_requested", "plain"])
@pytest.mark.parametrize("verdict", list(Verdict), ids=lambda v: v.value)
def test_no_verdict_yields_a_silent_incomplete_envelope(verdict: Verdict, render_requested: bool) -> None:
    envelope = _envelope(verdict=verdict, render_requested=render_requested)
    violations = _check_incompleteness_coherence(envelope)
    assert not violations, (
        f"verdict={verdict.value} render_requested={render_requested} produced an envelope "
        f"that violates ADR-0009:\n  " + "\n  ".join(violations) + "\n\n"
        f"  status={envelope['status']!r} hints={envelope['operator_hints']}\n\n"
        "An unfetched URL is an unfinished job. If a new verdict or terminal outcome "
        "can reach `retrieval_incomplete`, it must also reach a hint naming the remedy — "
        "`build_response`'s loudness floor is the backstop, so this failing means the "
        "floor itself regressed."
    )


def test_the_sweep_reaches_the_incomplete_branch_often() -> None:
    """Non-vacuity, with a floor rather than a mere `> 0`.

    Every rule in the coherence check is guarded by `retrieval_incomplete`, so
    a sweep in which nothing is incomplete passes while asserting nothing. A
    bare "at least one" would also survive a change that collapsed the space to
    a single case, which is most of the value gone; the floor is set well below
    the 26 observed so ordinary reclassification does not trip it.
    """
    incomplete = [
        (v.value, rr) for v in Verdict for rr in (True, False) if _envelope(verdict=v, render_requested=rr)["retrieval_incomplete"]
    ]
    assert len(incomplete) >= 15, (
        f"only {len(incomplete)} of {len(list(Verdict)) * 2} combinations reach "
        f"`retrieval_incomplete` ({incomplete}) — the sweep above is now checking "
        "far less than it was written to check. Either verdicts stopped being "
        "classified as incomplete, or the sweep stopped reaching the builder."
    )


def test_the_floor_is_what_makes_this_pass() -> None:
    """Mutation check — prove the sweep would go red without the backstop.

    Without this, a refactor that deleted the loudness floor would leave the
    sweep green if (and only if) every silent combination happened to be
    unreachable that week — a guard whose passing says nothing about whether it
    is doing any work. Asserting the CHECK discriminates on the exact envelope
    shape the floor produces keeps the two coupled.
    """
    silent = {
        "status": "failed",
        "retrieval_incomplete": True,
        "narrative": "raw → dns_error (0ms).",
        "operator_hints": [],
    }
    assert _check_incompleteness_coherence(silent), "the coherence check no longer objects to a hintless incomplete envelope"

    loud = dict(silent, operator_hints=["retrieval_incomplete"])
    assert not _check_incompleteness_coherence(loud), "the coherence check objects to a properly-hinted envelope"
