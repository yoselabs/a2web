"""A spent budget is an unfinished job, not an outcome — the ADR-0009 promise.

`_run_pipeline`'s `except DeadlineExceeded` is six lines carrying one of the
repository's louder claims:

    ADR-0009: a spent budget is an UNFINISHED JOB, never an outcome. Fall
    through to the same terminal machinery every other failure uses, so the
    caller gets `status: failed` + `retrieval_incomplete` + a loud hint rather
    than a truncated success or an exception.

**Every one of those six lines was uncovered.** `test_fetch_deadline.py` asserts
the exception is RAISED — by `_check_deadline`, `_within_budget`,
`_remaining_budget` — and nothing asserted it is CAUGHT, or that catching it
produces the envelope the comment describes. The helper was tested; the wiring
was not. That is the third instance of this shape found in one day (the
un-wired `strip_handles`, the un-run archive dispatch, this), which is why it
is worth naming in a docstring rather than just fixing.

**What the claim is worth checking against.** It promises three things and the
third is easy to lose: not a truncated success, not an exception. A raised
`DeadlineExceeded` escaping `fetch()` would be an unhandled error at the MCP
tool boundary — converted by `guard_tool` into an `UnexpectedDefect`, which
reads to a caller as a2web malfunctioning rather than as a page that took too
long. Both are failures; only one tells the truth.

Measured behaviour, pinned here rather than assumed: the deadline observation
classifies terminal as `wall`, so the envelope carries `try_user_browser`
alongside `fetch_deadline_exceeded`. That is deliberate under ADR-0009's
asymmetry — a budget that expired mid-ladder genuinely may be a site a user's
own browser can reach, and over-warning is the cheap direction.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.fetcher import DeadlineExceeded
from a2web.fetcher import pipeline as pipeline_mod
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.llm_eval.contract import _check_incompleteness_coherence
from a2web.models import FetchStatus
from tests.conftest import make_default_state


def _fc() -> FetchContext:
    return FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
        ),
        resources=FetchResources(
            sqlite=None,
        ),
        url="https://slow.example/page",
        final_url="https://slow.example/page",
    )


async def _expire(monkeypatch: pytest.MonkeyPatch, *, about_to: str = "tier:jina"):
    """Make the phase sequence expire, then run the real coordinator.

    Patched on the OWNING module, not on the `a2web.fetcher` re-export: a
    re-export is a second binding, and setting it would leave `_run_pipeline`'s
    own view of `_run_phases` untouched.
    """

    async def _boom(fc: FetchContext, *, state: object) -> None:
        del fc, state
        raise DeadlineExceeded(about_to)

    monkeypatch.setattr(pipeline_mod, "_run_phases", _boom)
    return await pipeline_mod._run_pipeline(_fc(), state=make_default_state())


async def test_the_deadline_does_not_escape_as_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The half most easily lost: a slow page is not a2web malfunctioning.

    If `DeadlineExceeded` propagated, `guard_tool` would quarantine it into an
    `UnexpectedDefect` at the tool boundary — telling the caller a2web broke
    rather than that the page took too long.
    """
    response = await _expire(monkeypatch)
    assert response is not None


async def test_a_spent_budget_is_a_failure_not_a_truncated_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = await _expire(monkeypatch)
    assert response.status is FetchStatus.failed
    assert response.retrieval_incomplete is True, (
        "a fetch that ran out of budget reported a complete result. ADR-0009: a spent "
        "budget is an unfinished job — the caller must not be able to read it as an answer."
    )


async def test_the_envelope_names_the_budget_and_the_remedy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both hints, and the reason there are two.

    `fetch_deadline_exceeded` says what happened; `try_user_browser` says what
    to do about it. An envelope carrying only the first is diagnosable but not
    actionable, which is the distinction ADR-0009's hint severity encodes.
    """
    response = await _expire(monkeypatch)
    codes = {h.code for h in response.operator_hints}
    assert "fetch_deadline_exceeded" in codes, f"the budget expiry is not named in the hints: {sorted(codes)}"
    assert "try_user_browser" in codes, f"no remedy offered for an expired budget: {sorted(codes)}"
    assert response.narrative.strip(), "an expired budget left no prose explanation"


async def test_the_deadline_envelope_is_coherent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cross-checked against the shared rule, not a local restatement.

    `_check_incompleteness_coherence` is what `make bench` and the replay
    corpora use. Asserting through it means this path cannot drift away from
    every other failure path's definition of "declared its incompleteness".
    """
    response = await _expire(monkeypatch)
    envelope = {
        "status": getattr(response.status, "value", response.status),
        "retrieval_incomplete": response.retrieval_incomplete,
        "narrative": response.narrative,
        "operator_hints": [h.code for h in response.operator_hints],
    }
    assert not _check_incompleteness_coherence(envelope)


async def test_the_hint_is_not_duplicated_when_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_record_deadline` guards on `_has_hint`. Without the guard a retry path
    that expired twice would emit two identical hints, and the TSV block an
    agent reads would show the same instruction twice."""
    response = await _expire(monkeypatch)
    codes = [h.code for h in response.operator_hints]
    assert codes.count("fetch_deadline_exceeded") == 1, f"duplicate deadline hints: {codes}"


async def test_the_envelope_says_TIMEOUT_and_not_merely_other(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cause survives, not just the fact of failure — added after a mutation.

    The first five tests here all passed with `_record_deadline`'s
    `fc.observe(...)` deleted, because the terminal classifier still reached
    `wall` from the empty log and every ADR-0009 signal still fired. What
    changed invisibly was the CAUSE:

        with the observation:  resolved_verdict=timeout   summary: verdict=timeout
        without it:            resolved_verdict=other     summary: verdict=other

    `other` is the verdict vocabulary's shrug. A caller told `failed` +
    `retrieval_incomplete` + `try_user_browser` would do the same thing either
    way, so no ADR-0009 assertion could catch it — but an operator reading
    `verdict=other` cannot tell a budget expiry from an unclassified defect,
    and would tune the wrong thing. Tier-truthfulness applies to the reason as
    well as the status.

    Worth stating that this test exists because the mutation found the hole in
    the TESTS, not in the product. Removing an observation is exactly the kind
    of "it's only telemetry" edit that looks free.
    """
    response = await _expire(monkeypatch)
    assert "verdict=timeout" in response.diagnostics_summary, (
        f"the deadline's cause was laundered: {response.diagnostics_summary!r}. "
        "`_record_deadline`'s observation is what carries `timeout` into the resolved "
        "verdict; without it the envelope reports the generic `other` and an operator "
        "cannot tell an expired budget from an unclassified failure."
    )
