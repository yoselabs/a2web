"""Proxy pool — route resolution + per-proxy health.

Two layers:
- `policy.resolve_route` is pure (settings → ResolvedRoute). Unit-testable.
- `pool.ProxyPool` adds health/quarantine state. Lazy via `state.ensure_proxy_pool`.
"""

from .policy import ResolvedRoute, resolve_route
from .pool import ProxyHandle, ProxyPool

__all__ = ["ProxyHandle", "ProxyPool", "ResolvedRoute", "resolve_route"]
