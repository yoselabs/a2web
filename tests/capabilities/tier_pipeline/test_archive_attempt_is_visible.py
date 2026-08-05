"""A failed archive dispatch must leave a row saying it was tried.

**The divergence and why its reason expired.** `_dispatch_archive` appended a
`Diagnostic` only when the archive WON. Browser, paid and the tier loop have
always appended unconditionally. The docstring justified it: a failed escalation
is "tried, didn't help" and "should not displace the originating verdict".

That reason stopped being true and the prose outlived it. `resolve_verdict`
reads `Observation`s, not `Diagnostic`s — `decision_log.py` filters on
`ObservationKind` — and the verdict became a pure projection of the decision log
in v0.23. A `Diagnostic` has no path into verdict resolution at all, so nothing
could have been displaced. Justification surviving the refactor that invalidated
it, which is the same shape as a stale allowlist entry: prose that reads as a
decision while protecting nothing.

**What the silence cost.** ADR-0009 makes the diagnostics list the place "what
did you try" lives. Without the row, *"we never tried the archive"* and *"we
tried and it did not help"* render identically. That is the cheap half of the
ADR-0009 harm — nobody is handed a wrong answer — but it is the same direction,
and it is the half that makes the expensive half hard to debug.

**Why this file exists rather than a delta in an existing test.** The fix landed
with all 1703 tests still green, though the closed bd issue a2web-3b6 predicted
`diagnostics_summary` deltas. The absence was the finding: the one test named
for a failed archive dispatch fakes `_dispatch_archive` ITSELF, so the real
function never runs and the branch had no coverage at all. This fakes the archive
TIER instead and lets the real dispatch execute — the difference between testing
a caller's handling of a result and testing the code that produces it.
"""

from __future__ import annotations

import pytest

from a2web.fetcher.retrieval.escalate.archive import _dispatch_archive
from a2web.models import Diagnostic, Verdict
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state


class _ArchiveTier:
    """The real archive tier's seam, returning a fixed outcome."""

    name = "archive"

    def __init__(self, result: TierResult) -> None:
        self._result = result

    async def fetch(self, url: str, *, state: object, **_kw: object) -> TierResult:
        del url, state
        return self._result


async def _dispatch(monkeypatch: pytest.MonkeyPatch, result: TierResult) -> list[Diagnostic]:
    monkeypatch.setitem(REGISTRY, "archive", _ArchiveTier(result))
    diagnostics: list[Diagnostic] = []
    await _dispatch_archive(
        "https://example.com/gone",
        state=make_default_state(),
        start_perf=0.0,
        diagnostics=diagnostics,
    )
    return diagnostics


@pytest.mark.parametrize(
    "verdict",
    [Verdict.not_found, Verdict.timeout, Verdict.connection_error, Verdict.anti_bot],
    ids=lambda v: v.value,
)
async def test_a_failed_dispatch_still_records_the_attempt(monkeypatch: pytest.MonkeyPatch, verdict: Verdict) -> None:
    rows = await _dispatch(
        monkeypatch, TierResult(body=b"", content_type="", verdict=verdict, status_code=404, final_url="https://example.com/gone")
    )

    assert len(rows) == 1, (
        f"a `{verdict.value}` archive dispatch left no diagnostic row. The caller cannot "
        "now distinguish 'the archive was never tried' from 'it was tried and did not "
        "help' — ADR-0009: the diagnostics list is where 'what did you try' lives."
    )
    assert rows[0].step == "archive"
    assert rows[0].verdict is verdict, "the row must carry the FAILING verdict, not a laundered one"


async def test_an_ok_dispatch_with_no_payload_also_records() -> None:
    """The second failure mode, and it is not the same branch.

    `verdict is ok` with `pre_rendered is None` returns unsuccessfully too — a
    snapshot that resolved but rendered nothing. It leaves a row like any other
    attempt, and the row honestly says `ok`, because that is what the tier
    reported; the emptiness is visible from the absence of installed content,
    not by rewriting the tier's own verdict (tier-truthfulness).
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        rows = await _dispatch(
            monkeypatch,
            TierResult(
                body=b"",
                content_type="text/html",
                verdict=Verdict.ok,
                status_code=200,
                final_url="https://example.com/gone",
                pre_rendered=None,
            ),
        )
    finally:
        monkeypatch.undo()
    assert len(rows) == 1
    assert rows[0].verdict is Verdict.ok


async def test_a_successful_dispatch_still_records_exactly_one_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-vacuity, and a real regression risk.

    Moving the append above the success check is a two-line edit that could
    easily leave the original append in place, producing two rows per successful
    archive hit — a duplicate no other test would notice.
    """
    rows = await _dispatch(
        monkeypatch,
        TierResult(
            body=b"<html>archived</html>",
            content_type="text/html",
            verdict=Verdict.ok,
            status_code=200,
            final_url="https://web.archive.org/web/2020/https://example.com/gone",
            pre_rendered=Rendered(content_md="# Archived\n\nSome body."),
        ),
    )
    assert len(rows) == 1, f"expected exactly one archive diagnostic, got {len(rows)}"
    assert rows[0].verdict is Verdict.ok
