"""A site answering badly must not quarantine the proxy that carried the answer.

`ProxyPool.report(handle, success=...)` feeds the per-proxy circuit breaker:
three consecutive failures quarantine that proxy for 600 seconds. So the boolean
a2web passes is a claim about **the egress**, not about the fetch — and the two
diverge constantly. A `not_found`, a `paywall`, an `anti_bot` challenge page:
the proxy did its job perfectly and delivered the site's real answer.

**This was found by mutation, and it is the reason the file exists.** During
`decompose-fetcher-into-files` §7 the lease/report protocol moved out of
`_phase_tier_loop` into `retrieval/proxy_lease.py`. Four mutations of the moved
code went red. The fifth — replacing the verdict test with a flat
`success=False`, i.e. reporting EVERY dispatch as an egress failure — passed the
entire suite, 1727 tests.

What that mutation does in production: three 404s in a row through one proxy
quarantine it for ten minutes. Every host routed there then falls back, or, on a
`proxy_required` route, has its tier skipped entirely — which is
`test_required_proxy_is_never_bypassed`'s scenario reached by a bug rather than
by an operator's dead pool. A fetcher walking a cascade of tiers over
sometimes-404ing sites would do this to itself continuously.

**`tests/packages/test_proxy_routing.py` does not cover it, and could not.** It
tests the pool: three `report(success=False)` calls quarantine, a success
resets. Every one of those calls passes the boolean literally. The question here
is which VERDICTS a2web turns into that boolean — a wiring property, invisible
to a test that supplies the boolean itself. The fifth
helper-tested-but-wiring-untested gap found this session, and the same shape as
the other four.
"""

from __future__ import annotations

import pytest

from a2web.fetcher.retrieval.proxy_lease import report_lease
from a2web.models import Verdict
from a2web.packages.proxy_routing import _FAILURE_THRESHOLD, ProxyHandle, ProxyPool
from a2web.tiers import TierResult

_HANDLE = ProxyHandle(proxy_url="http://proxy.invalid:8080", proxy_id="eu", matched_rule_index=0)

#: The egress itself failed — nothing came back through it. These are the only
#: verdicts that say anything about the proxy.
_EGRESS_VERDICTS = frozenset({Verdict.connection_error, Verdict.timeout, Verdict.proxy_unavailable})

#: `dns_error` is genuinely ambiguous and is deliberately NOT in the set above.
#: With an HTTP proxy the name is usually resolved AT the proxy, so a DNS failure
#: can mean the egress is broken — but it far more often means the host does not
#: exist, and quarantining a healthy proxy over a typo'd URL is the worse error.
#: The false-positive asymmetry decides it, the same way it decides
#: empty-vs-wall. Recorded here rather than left to be rediscovered; changing it
#: is a policy decision, not a bug fix.
_AMBIGUOUS = frozenset({Verdict.dns_error})

#: Everything else: the site answered, badly or well. Derived by subtraction so a
#: NEW verdict lands here by default and this file goes red until someone
#: classifies it — the safe direction, since the default is "do not blame the
#: proxy" and the cost of being wrong is a stale breaker rather than a dead one.
_ORIGIN_VERDICTS = [v for v in Verdict if v not in _EGRESS_VERDICTS and v not in _AMBIGUOUS]


def _pool() -> ProxyPool:
    return ProxyPool(routes=[], proxies={})


def _quarantined(pool: ProxyPool) -> bool:
    health = pool.health.get("eu")
    return health is not None and health.quarantined_until > 0.0


def _report_n(pool: ProxyPool, verdict: Verdict, n: int) -> None:
    for _ in range(n):
        result = TierResult(body=b"", content_type=None, status_code=None, final_url="https://x.example", verdict=verdict)
        report_lease(pool, _HANDLE, result)


def test_the_threshold_is_reachable_at_all() -> None:
    """Non-vacuity floor: prove quarantine CAN happen through this seam.

    Without this, every assertion below could pass because `report_lease` is
    broken in the other direction — never opening the breaker for anything — and
    the file would read as coverage while pinning nothing.
    """
    pool = _pool()
    _report_n(pool, Verdict.connection_error, _FAILURE_THRESHOLD)
    assert _quarantined(pool), (
        f"{_FAILURE_THRESHOLD} connection errors did not quarantine the proxy. "
        "The breaker is unreachable through `report_lease`, so the tests below "
        "prove nothing about which verdicts avoid it."
    )


@pytest.mark.parametrize("verdict", _ORIGIN_VERDICTS, ids=lambda v: v.value)
def test_a_site_answering_badly_never_quarantines_the_proxy(verdict: Verdict) -> None:
    """The mutation that survived, pinned.

    Well past the threshold on purpose: a walk over `TIER_ORDER` against a
    404ing host reports several times per fetch, so the realistic failure is not
    a near-miss.
    """
    pool = _pool()
    _report_n(pool, verdict, _FAILURE_THRESHOLD * 3)
    assert not _quarantined(pool), (
        f"`{verdict.value}` quarantined the egress. The site answered — the proxy "
        "carried that answer and is healthy. Quarantining it takes a working proxy out "
        "of rotation for 10 minutes, and on a `proxy_required` route that means the "
        "tier is skipped entirely (ADR-0009: an unfetched URL)."
    )


@pytest.mark.parametrize("verdict", sorted(_EGRESS_VERDICTS, key=lambda v: v.value), ids=lambda v: v.value)
def test_an_egress_failure_still_opens_the_breaker(verdict: Verdict) -> None:
    """The other direction, which is what makes the test above a distinction.

    A guard that only asserts "nothing quarantines" is satisfied by a
    `report_lease` reporting success unconditionally — the opposite bug, where a
    genuinely dead proxy is retried forever.
    """
    pool = _pool()
    _report_n(pool, verdict, _FAILURE_THRESHOLD)
    assert _quarantined(pool), (
        f"`{verdict.value}` did not open the breaker. This verdict means the request did "
        "not complete through this egress; not counting it leaves a dead proxy in "
        "rotation, retried on every fetch until the whole cascade times out."
    )


def test_a_success_resets_an_accumulating_proxy() -> None:
    """Consecutive, not cumulative — otherwise a long-lived pool quarantines eventually."""
    pool = _pool()
    _report_n(pool, Verdict.connection_error, _FAILURE_THRESHOLD - 1)
    _report_n(pool, Verdict.ok, 1)
    _report_n(pool, Verdict.connection_error, _FAILURE_THRESHOLD - 1)
    assert not _quarantined(pool), (
        "an intervening success did not reset the failure count. Failures must be "
        "CONSECUTIVE — cumulative counting quarantines every proxy given enough uptime."
    )
