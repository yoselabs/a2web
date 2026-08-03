"""ADR-0009 coherence, over every case the replay corpora can reproduce.

**Why this test exists alongside the unit tests.** `check_envelope_contract`'s
coherence rules are exercised in `tests/capabilities/output_benchmark/` against
hand-built dicts — which proves the rules *fire*, and nothing at all about
whether the real pipeline ever produces the shape they forbid. A rule verified
only against dicts its author wrote is the fixture-as-oracle failure: it
encodes the same assumption as the code, authored by the same person at the
same moment.

This runs the rules over envelopes produced by the REAL orchestrator, gate and
tier ladder driving frozen bytes. Foreign provenance: nothing here was written
to satisfy the check, and the corpora predate it by months.

**And why it is not just a bench axis.** The bench is live-network, spends LLM
quota, and is deliberately outside `make check` — so a coherence regression
would have surfaced only when someone chose to run it. Here it gates every
push, at the cost of one replay pass the suite was already paying for.

**On the projection-vs-wire seam.** `replay.observe` and the live bench's
`runner._observe_for_contract` share their key names by contract (that is the
whole point of `case_contract`'s vocabulary), so the projection can be handed
to the wire checker directly. Two differences, both harmless here: the
projection always carries `status` and `retrieval_incomplete` where the wire
omits them at their defaults, and its `operator_hints` are bare codes rather
than objects. The coherence rules read presence and truthiness, so both shapes
answer the same question. What this does NOT do is re-implement the rules for
the projection — one implementation, two callers, for the reason
`case_contract`'s docstring gives: a second copy drifts, and then a key means
two things.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.llm_eval.contract import _check_incompleteness_coherence
from eval._capture.corpus import load_corpus
from tests.eval_replay.replay import replay_case

_EVAL = Path(__file__).resolve().parents[2] / "eval" / "corpus"
_CASES = [*load_corpus(_EVAL / "regression"), *load_corpus(_EVAL / "breaking")]


@pytest.mark.skipif(not _CASES, reason="no replayable cases captured yet")
@pytest.mark.parametrize("case", _CASES, ids=[c.slug for c in _CASES])
async def test_replayed_envelope_is_coherent(monkeypatch: pytest.MonkeyPatch, case) -> None:
    """No case, in either branch, admits incompleteness silently."""
    observed = await replay_case(monkeypatch, case)
    violations = _check_incompleteness_coherence(observed)
    assert not violations, (
        f"{case.slug} replayed an envelope that violates ADR-0009:\n  " + "\n  ".join(violations) + "\n\n"
        "This is the cardinal product invariant: a URL a2web did not retrieve is an "
        "unfinished job, and the caller must never be able to mistake it for a "
        "complete answer. Fix the pipeline, not this assertion."
    )


async def test_at_least_one_case_exercises_the_incomplete_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-vacuity — the check above must be running on something.

    Every rule in `_check_incompleteness_coherence` is guarded by
    `retrieval_incomplete`, so a corpus in which nothing fails would pass the
    parametrized test while asserting literally nothing. That is the failure
    this repo keeps finding (30 of 32 architecture tests once passed against an
    empty source tree), and it is a live risk here: the incomplete branch is
    carried by a handful of wall cases, and a capture refresh that let them all
    start succeeding would silently empty this file of meaning.
    """
    incomplete = []
    for case in _CASES:
        observed = await replay_case(monkeypatch, case)
        if observed.get("retrieval_incomplete"):
            incomplete.append(case.slug)

    assert incomplete, (
        "No replayable case produces `retrieval_incomplete` any more, so the "
        "coherence check ran over nothing. Either a wall case was re-captured "
        "into a success, or the flag stopped being set — the second would be an "
        "ADR-0009 regression that this file was written to catch."
    )
