"""A host that REQUIRES a proxy is skipped, not fetched directly.

**Two properties, and the first is a safety property rather than a quality one.**
`ProxyPool.acquire` returns `None` in exactly one situation: the host's route
resolves to a proxy, every proxy in its chain is circuit-broken, AND the rule
sets `proxy_required`. An operator writes `proxy_required` when a direct
connection is not merely worse but wrong — the request would leave from a2web's
own address, defeating the routing policy that made them configure it.

So the tier must be SKIPPED. Falling through to `direct` would be a silent
policy violation: the fetch succeeds, the caller is happy, and the operator's
requirement was quietly ignored on exactly the requests it existed for.

The second property is ADR-0009 visibility, and it is the same shape as the
archive-dispatch fix: the skip must leave a diagnostic row AND a decision-log
observation, so the caller can tell "this tier was skipped because its proxies
were dead" from "this tier was never in the ladder".

**Why the observation is not merely telemetry.** Measured on the deadline path
hours before this file was written: deleting an observation left every ADR-0009
signal firing while the resolved verdict silently degraded from the real cause
to the generic `other`. The decision log is what carries WHY. A skip that
records only a `Diagnostic` would leave the verdict shrugging.

These 3 statements were the last uncovered block in `tier_walk.py`.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from a2web.fetcher.context import FetchContext
from a2web.fetcher.retrieval.tier_walk import _phase_tier_loop
from a2web.models import Verdict
from a2web.packages.proxy_routing import _ProxyHealth
from a2web.settings import AppSettings, ProxyEntry, RouteRule
from a2web.state import AppState
from tests.conftest import make_default_state


def _kill(state: AppState, proxy_id: str) -> None:
    """Mark a proxy dead the way the circuit breaker would.

    Deliberately not by faking `acquire`: a faked `acquire` would test this
    file's idea of the pool rather than the pool, and the whole question here is
    what the real pool returns when a required proxy is unavailable.
    """
    state.proxy_pool.health.setdefault(proxy_id, _ProxyHealth()).dead = True


def _state_with_a_dead_required_proxy() -> AppState:
    settings = AppSettings(
        proxies={"eu": ProxyEntry(url="http://proxy.invalid:8080", region="eu")},
        routes=[RouteRule(host="locked.example", proxy="eu", proxy_required=True)],
    )
    state = make_default_state(settings=settings)
    _kill(state, "eu")
    return state


def _fc() -> FetchContext:
    return FetchContext(
        started_at=datetime.now(UTC),
        start_perf=time.perf_counter(),
        profile_hash="x",
        sqlite=None,
        bypass_cache=True,
        url="https://locked.example/page",
        final_url="https://locked.example/page",
    )


def test_acquire_returns_none_only_when_required_and_all_dead() -> None:
    """Pin the precondition, so the tests below cannot pass for the wrong reason.

    If `proxy_required` were dropped or the health marking stopped working,
    `acquire` would hand back a `direct` handle and the walk would fetch
    normally — the assertions below would then be exercising the ordinary path
    while appearing to cover the skip.
    """
    state = _state_with_a_dead_required_proxy()
    assert state.proxy_pool.acquire("locked.example", "raw") is None

    # And the inverse: an unrequired route falls back to direct rather than None,
    # so `None` genuinely means "required and unavailable".
    relaxed = make_default_state(
        settings=AppSettings(
            proxies={"eu": ProxyEntry(url="http://proxy.invalid:8080")},
            routes=[RouteRule(host="open.example", proxy="eu", proxy_required=False)],
        )
    )
    _kill(relaxed, "eu")
    handle = relaxed.proxy_pool.acquire("open.example", "raw")
    assert handle is not None and handle.proxy_id == "direct"


async def test_the_skip_leaves_a_row_and_an_observation() -> None:
    fc = _fc()
    await _phase_tier_loop(fc, state=_state_with_a_dead_required_proxy())

    rows = [d for d in fc.diagnostics if d.verdict is Verdict.proxy_unavailable]
    assert rows, (
        "a tier skipped for a dead required proxy left no diagnostic row. The caller "
        "cannot distinguish 'skipped because its proxies were dead' from 'never in the "
        "ladder' — the gap-where-an-attempt-was shape (ADR-0009)."
    )
    assert rows[0].extra.get("reason") == "all_proxies_dead_required"

    observed = [o for o in fc.observations if o.verdict is Verdict.proxy_unavailable]
    assert observed, (
        "the skip left a diagnostic but no OBSERVATION. `resolve_verdict` reads the "
        "decision log, not diagnostics, so without this the fetch reports the generic "
        "`other` and the real cause is lost."
    )
    assert fc.resolved_verdict() is Verdict.proxy_unavailable


async def test_no_tier_fetched_the_host_directly() -> None:
    """The safety half: skipping means NOT fetching, not fetching another way."""
    fc = _fc()
    await _phase_tier_loop(fc, state=_state_with_a_dead_required_proxy())

    assert fc.tier_used == "none", f"a tier ran despite its required proxy being unavailable: {fc.tier_used!r}"
    assert not fc.body, "content was retrieved for a host whose required proxy was dead — the routing policy was bypassed"
