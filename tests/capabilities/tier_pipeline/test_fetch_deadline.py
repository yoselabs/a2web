"""One fetch is bounded as a whole, not just hop by hop.

Every hop had its own timeout; nothing bounded their SUM. Summing the constants
actually in the tree — github 15 + raw 10 + jina 15 + archive 12 + browser
launch 45 + page 30 + zyte 60 + firecrawl 40 + llm 180 — gives a 407s worst-case
serial walk, with the caller holding an open MCP tool call the whole time. The
default deadline (480s) sits above that measurement deliberately: it is a
backstop against a pathological walk, not a second and tighter budget that would
cut healthy work short.

Two properties matter, and they are separate tests because they can fail
independently:

- a spent budget stops the NEXT dispatch (`test_no_tier_is_dispatched_after_expiry`);
- a spent budget produces the ADR-0009 failure envelope rather than an
  exception or a truncated success (`test_expiry_reports_an_unfinished_job`).
"""

from __future__ import annotations

import time

import pytest

from a2web import fetcher
from a2web.fetcher import DeadlineExceeded, FetchContext, _check_deadline, _remaining_budget, _within_budget
from a2web.models import Verdict


def _fc(*, deadline_perf: float | None) -> FetchContext:
    """A context carrying only what the deadline helpers read."""
    return FetchContext(
        started_at=fetcher.datetime.now(fetcher.UTC),
        start_perf=time.perf_counter(),
        profile_hash="test",
        sqlite=None,
        bypass_cache=True,
        url="https://example.com/slow",
        final_url="https://example.com/slow",
        deadline_perf=deadline_perf,
    )


def test_a_spent_budget_refuses_the_next_dispatch() -> None:
    """THE regression, at its narrowest."""
    fc = _fc(deadline_perf=time.perf_counter() - 1)  # already past
    with pytest.raises(DeadlineExceeded, match="tier:jina"):
        _check_deadline(fc, about_to="tier:jina")


def test_a_live_budget_allows_dispatch() -> None:
    """Anti-vacuity: a deadline that always fires is not a deadline."""
    fc = _fc(deadline_perf=time.perf_counter() + 60)
    _check_deadline(fc, about_to="tier:jina")  # must not raise
    remaining = _remaining_budget(fc)
    assert remaining is not None and remaining > 0


def test_the_deadline_can_be_disabled() -> None:
    """`fetch_deadline_s <= 0` → no deadline at all, never a zero budget."""
    fc = _fc(deadline_perf=None)
    assert _remaining_budget(fc) is None
    _check_deadline(fc, about_to="tier:jina")  # must not raise


async def test_a_hop_is_capped_by_the_remaining_budget() -> None:
    """`min(own timeout, remaining)` — the hop's own bound is not the only one.

    A tier that would happily wait 60s must not, when 0.2s of budget is left.
    Enforced at the dispatch site rather than inside each tier: there are eight
    tiers plus the handlers, and a bound re-implemented nine times is a bound
    that will be missing from the tenth.
    """
    fc = _fc(deadline_perf=time.perf_counter() + 0.2)

    started = time.monotonic()
    with pytest.raises(DeadlineExceeded):
        async with _within_budget(fc, about_to="tier:zyte"):
            await fetcher.asyncio.sleep(60)
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"the remaining budget did not cap the hop — waited {elapsed:.1f}s"


async def test_a_hop_that_finishes_in_budget_is_untouched() -> None:
    """Anti-vacuity for the cap: it must not disturb work that fits."""
    fc = _fc(deadline_perf=time.perf_counter() + 30)
    async with _within_budget(fc, about_to="tier:raw"):
        await fetcher.asyncio.sleep(0)


async def test_no_tier_is_dispatched_after_expiry() -> None:
    """Task 3.6, driven through the real dispatch wrapper.

    The point is not that the hop is cancelled — it is that the hop never
    STARTS. A budget with nothing left must not pay for another network call.
    """
    fc = _fc(deadline_perf=time.perf_counter() - 1)
    dispatched = False

    with pytest.raises(DeadlineExceeded):
        async with _within_budget(fc, about_to="tier:browser"):
            dispatched = True  # pragma: no cover — must be unreachable

    assert not dispatched, "a hop was started with no budget left to finish it"


async def test_expiry_reports_an_unfinished_job() -> None:
    """ADR-0009: a spent budget is an unfinished job, never an outcome.

    It must reach the caller as the same loud failure every other miss uses —
    a critical hint naming the budget and the stage that was about to start —
    not as an exception and not as a truncated success.
    """
    from a2web.settings import AppSettings
    from tests.conftest import make_default_state

    state = make_default_state(AppSettings(fetch_deadline_s=45))
    fc = _fc(deadline_perf=time.perf_counter() - 1)

    await fetcher._record_deadline(fc, about_to="tier:browser", state=state)

    hint = next((h for h in fc.operator_hints if h.code == "fetch_deadline_exceeded"), None)
    assert hint is not None, "a spent budget must never be silent (ADR-0009)"
    assert hint.severity == "critical"
    assert "45s" in hint.message, "the hint must name the budget that was spent"
    assert "tier:browser" in hint.message, "and the stage it stopped before — that is the actionable part"
    assert "NOT retrieved" in hint.message
    # a2web cannot see whether the site is slow; only that it ran out of budget.
    assert "unreachable" not in hint.message.lower()

    assert any(o.verdict is Verdict.timeout for o in fc.observations), "the decision log must record the expiry"
