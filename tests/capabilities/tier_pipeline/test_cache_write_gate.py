"""Never write below the quality gate — the invariant with no cell anywhere.

**Why this file exists.** `docs/findings/2026-08-02-invariant-cell-mapping.md`
enumerates a2web's twelve first-class invariants and names the corpus cells that
can catch each. Two still have zero, and this is one of them: *"never cache
below the gate"* — recorded there as **"none, in any corpus. Neither harness
observes the cache."** Checked again 2026-08-03: no test file in the repository
so much as named `_phase_cache_write`. Zero cells and zero unit tests, for a
rule on CLAUDE.md's **Never** list.

The harm is worse than an ordinary miss and that is the reason to spend a file
on it. A block page that reaches the cache is not one bad answer — it is a
**persistent** silent miss, served to every caller for the whole TTL without a
single further network request to notice it was wrong. ADR-0009's failure mode
with a repeat.

**The gate is one boolean conjunction, so each clause is tested as a clause.**
A conjunction is exactly the shape where a test of the happy path plus a test
of one failure proves nothing about the other four — and where deleting a term
leaves every other test green.

**The subtle one is `_confirmed_empty` / `_small_page`, and it is a real trap.**
Both promotions in `fetcher/verdict/promotions.py` deliberately leave the
verdict at `length_floor` — *not* because the verdict is right, but because
`_phase_cache_write` reads it and would otherwise cache a promotion that is
meant to be wire-only. Two comments say so. Nothing enforced it. A future
tidy-up that "fixes" the verdict to `ok` at the promotion site is a one-line
change, obviously correct in isolation, and it would start persisting empty
results — the exact repeating silent miss the design calls out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext
from a2web.fetcher.retrieval.cache import _phase_cache_write
from a2web.models import CacheState, Verdict
from tests.conftest import make_default_state


@dataclass
class _RecordingSqlite:
    """Stands in for `SqliteResource`, recording only whether `put` was called.

    A spy rather than a mock: the question is binary — did anything reach the
    cache — and a spy cannot accidentally assert the arguments and drift into
    testing `put`'s signature instead of the gate.
    """

    puts: list[str] = field(default_factory=list)

    async def put(self, url: str, profile_hash: str, **_kw: object) -> None:
        self.puts.append(url)


def _fc(*, verdict: Verdict, **overrides: object) -> FetchContext:
    fc = FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="p",
        sqlite=None,
        url="https://e.com/p",
        final_url="https://e.com/p",
        **{"bypass_cache": False, **overrides},  # type: ignore[arg-type]
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=verdict)
    fc.body = b"<html>a body long enough to be real</html>"
    fc.tier_used = "raw"
    return fc


async def _wrote(fc: FetchContext) -> bool:
    spy = _RecordingSqlite()
    fc.sqlite = spy  # type: ignore[assignment]
    await _phase_cache_write(fc, state=make_default_state())
    return bool(spy.puts)


async def test_a_clean_ok_fetch_is_cached() -> None:
    """The positive case, first — without it every assertion below is vacuous.

    A gate that never writes passes every "must not write" test in this file
    while making the cache useless.
    """
    assert await _wrote(_fc(verdict=Verdict.ok))


@pytest.mark.parametrize(
    "verdict",
    [Verdict.anti_bot, Verdict.block_page_detected, Verdict.paywall, Verdict.length_floor, Verdict.not_found, Verdict.rate_limited],
    ids=lambda v: v.value,
)
async def test_no_failing_verdict_reaches_the_cache(verdict: Verdict) -> None:
    """**The invariant itself.** A wall extracts to prose perfectly well, so
    nothing downstream of the cache can tell a stored block page from a stored
    article — which is why the check has to happen here, before the write."""
    assert not await _wrote(_fc(verdict=verdict)), (
        f"a `{verdict.value}` response reached the cache. It will now be served to every "
        "caller for the whole TTL with no network request to notice — a silent miss that "
        "repeats (CLAUDE.md: never bypass the quality gate when writing to cache)."
    )


async def test_a_promoted_empty_is_not_cached() -> None:
    """The trap the promotions' own comments describe and nothing enforced.

    `_phase_empty_promotion` sets `empty_confirmed` and deliberately leaves the
    verdict at `length_floor` **so that this gate declines it**. If a later
    change flips the verdict to `ok` at the promotion site — a one-line edit
    that looks obviously right — the promotion starts being persisted, and a
    wrongly-promoted empty becomes a repeating silent miss.
    """
    fc = _fc(verdict=Verdict.length_floor)
    fc.empty_confirmed = True
    assert not await _wrote(fc), (
        "a promoted empty result reached the cache. The promotion is wire-only by design; "
        "`promotions.py` leaves the verdict at `length_floor` specifically so this gate "
        "declines it. If the verdict was deliberately changed, this gate needs its own "
        "check on `empty_confirmed` — do not simply delete this test."
    )


async def test_a_promoted_small_page_is_not_cached() -> None:
    """Sibling of the above, same coupling, same one-line risk."""
    fc = _fc(verdict=Verdict.length_floor)
    fc.small_page_confirmed = True
    assert not await _wrote(fc), "a promoted complete-small-page reached the cache; the promotion is wire-only by design"


async def test_bypass_cache_does_not_write_either() -> None:
    """`bypass_cache` is read-side AND write-side.

    A live-only host (`is_live_only`) must not deposit a row on the way past,
    or the next non-bypassing caller is served the bypassed host's body — the
    setting would silently poison exactly the hosts it exists to keep fresh.
    """
    assert not await _wrote(_fc(verdict=Verdict.ok, bypass_cache=True))


async def test_a_cache_hit_is_not_rewritten() -> None:
    """Re-storing a hit would refresh the TTL on every read, so a row could
    never expire while it was being served — cache poisoning by popularity."""
    fc = _fc(verdict=Verdict.ok)
    fc.cache_state = CacheState.hit
    assert not await _wrote(fc)


async def test_an_archive_body_is_not_cached() -> None:
    """A Wayback body is a SNAPSHOT of another moment, and the cache has no
    field saying so. Stored, it becomes indistinguishable from a live fetch,
    and the `archive_snapshot_age` hint that warns about staleness is attached
    at response time — it would not fire on the subsequent cache hits."""
    fc = _fc(verdict=Verdict.ok)
    fc.tier_used = "archive"
    assert not await _wrote(fc)


async def test_an_empty_body_is_not_cached() -> None:
    """Storing zero bytes under an `ok` verdict is a cached blank page."""
    fc = _fc(verdict=Verdict.ok)
    fc.body = b""
    assert not await _wrote(fc)


async def test_no_sqlite_is_a_no_op_not_a_crash() -> None:
    """The cacheless configuration (`sqlite=None`) is legitimate — the CLI runs
    it — so the gate must decline rather than raise."""
    fc = _fc(verdict=Verdict.ok)
    await _phase_cache_write(fc, state=make_default_state())  # sqlite is still None
