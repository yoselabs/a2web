"""The lease/report protocol around a single tier dispatch.

`ProxyPool.acquire` hands out a lease and `ProxyPool.report` closes it with a
success verdict that feeds the per-proxy circuit breaker. The two calls sit at
opposite ends of a tier dispatch with the whole `tier.fetch` in between, so
inline they read as two unrelated statements — and the failure path of the
first (a required pool with every proxy dead) carries a diagnostic row AND a
decision-log observation that have to agree with each other.

Lifted out of `_phase_tier_loop` by `decompose-fetcher-into-files` §7. The
loop's job is the walk over `TIER_ORDER`; who supplies the egress for one hop
is a different question, and it was one of the five the census counted there.

**Not an `async with`, deliberately.** A context manager would pair the two
calls at the language level, which is the obvious shape and the wrong one: the
dead-pool path must SKIP the tier (`continue`), and a manager whose `__aenter__`
yields `None` still runs its body. The caller has to branch on the lease either
way, so the honest signature returns `None` and lets the caller `continue`.
"""

from __future__ import annotations

from ...decision_log import ObservationKind
from ...models import Diagnostic, Verdict
from ...packages.proxy_routing import ProxyHandle, ProxyPool
from ...tiers import TierResult
from ..context import FetchContext
from ..telemetry import _host

#: Verdicts that mean "the egress failed", not "the site answered badly". A 403
#: from the origin says nothing about the proxy and must not open its breaker.
_EGRESS_FAILURES = (Verdict.proxy_unavailable, Verdict.connection_error, Verdict.timeout)


def acquire_lease(fc: FetchContext, *, proxy_pool: ProxyPool, tier_name: str, tier_start_ms: int) -> ProxyHandle | None:
    """Lease an egress for one tier dispatch, or record why there is none.

    `None` means the host has a REQUIRED proxy pool and every member is dead —
    the tier must be skipped, not attempted directly. Skipping silently would
    make a dead pool indistinguishable from a tier that simply lost, so the miss
    is recorded twice on purpose: a `Diagnostic` row for the operator and a
    `tier_outcome` observation for the planner, which is the only reason
    `decide_next` can tell "we did not try" from "we tried and failed".
    """
    handle = proxy_pool.acquire(_host(fc.url) or "", tier_name)
    if handle is not None:
        return handle

    fc.diagnostics.append(
        Diagnostic(
            t_ms=tier_start_ms,
            step=tier_name,
            engine=None,
            host=_host(fc.url),
            proxy=None,
            verdict=Verdict.proxy_unavailable,
            dur_ms=0,
            extra={"reason": "all_proxies_dead_required"},
        )
    )
    fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.proxy_unavailable)
    return None


def report_lease(proxy_pool: ProxyPool, handle: ProxyHandle, tier_result: TierResult) -> None:
    """Close the lease with the verdict the breaker should see.

    The distinction that matters is egress-vs-origin: a `not_found` or `paywall`
    is the SITE answering, and reporting it as a proxy failure would open the
    breaker on a perfectly good egress after a handful of 404s.
    """
    proxy_pool.report(handle, success=tier_result.verdict not in _EGRESS_FAILURES)
