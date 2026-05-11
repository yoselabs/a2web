"""Proxy routing — pure resolution + stateful pool, in-tree microsofware.

Zero a2web-domain imports. Boundary input is Protocol-shaped — any
duck-typed entry/rule with the right attributes satisfies it. The a2web
seam (`proxy/policy.py`, `proxy/pool.py`) passes pydantic models from
`AppSettings` through directly.

Two layers:
- `policy.resolve_route` — pure, given routes + proxies, returns a
  decision (proxy_url, fallbacks, required-flag).
- `pool.ProxyPool` — stateful (per-proxy health, quarantine on
  consecutive failures) wrapper over the policy.
"""

from __future__ import annotations

from .policy import ProxyEntryShape, ResolvedRoute, RouteRuleShape, resolve_route
from .pool import ProxyHandle, ProxyPool

__all__ = (
    "ProxyEntryShape",
    "ProxyHandle",
    "ProxyPool",
    "ResolvedRoute",
    "RouteRuleShape",
    "resolve_route",
)
