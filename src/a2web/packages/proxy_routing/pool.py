"""Proxy pool — stateful layer over the pure route policy.

Tracks per-proxy health (alive | quarantined_until | dead). Three
consecutive failures quarantine for 600s. Health is in-memory only;
disk persistence is a future option.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .policy import ProxyEntryShape, ResolvedRoute, RouteRuleShape, resolve_route

_QUARANTINE_S = 600.0
_FAILURE_THRESHOLD = 3


@dataclass(slots=True)
class _ProxyHealth:
    quarantined_until: float = 0.0
    consecutive_failures: int = 0
    dead: bool = False

    def is_alive(self, now: float) -> bool:
        if self.dead:
            return False
        if self.quarantined_until and now < self.quarantined_until:
            return False
        return True


@dataclass(slots=True, frozen=True)
class ProxyHandle:
    """What a caller sees: the URL to use, the id to record, and the matched rule."""

    proxy_url: str | None
    proxy_id: str  # "direct" when proxy_url is None
    matched_rule_index: int | None


class ProxyPool:
    """Stateful proxy pool keyed off a route table + proxies map.

    Both `routes` and `proxies` are Protocol-shaped — any duck-typed
    source (pydantic, dataclass, dict-of-objects) works.
    """

    __slots__ = ("_proxies", "_routes", "health")

    def __init__(
        self,
        *,
        routes: list[RouteRuleShape],
        proxies: dict[str, ProxyEntryShape],
    ) -> None:
        self._routes = routes
        self._proxies = proxies
        self.health: dict[str, _ProxyHealth] = {}

    async def close(self) -> None:
        """No-op today; symmetric with other resources."""
        return None

    def resolve(self, host: str, tier: str) -> ResolvedRoute:
        return resolve_route(host, tier, routes=self._routes, proxies=self._proxies)

    def acquire(self, host: str, tier: str) -> ProxyHandle | None:
        """Walk primary + fallbacks; return first healthy or direct.

        Returns None when all proxies in the chain are unhealthy AND
        `proxy_required` is set.
        """
        route = self.resolve(host, tier)
        if route.proxy_id == "direct" or route.proxy_url is None:
            return ProxyHandle(
                proxy_url=None,
                proxy_id="direct",
                matched_rule_index=route.matched_rule_index,
            )

        chain: list[tuple[str, str]] = [(route.proxy_id or "", route.proxy_url)]
        for fb_id in route.fallback:
            entry = self._proxies.get(fb_id)
            if entry is None:
                continue
            chain.append((fb_id, entry.url))

        now = time.monotonic()
        for proxy_id, proxy_url in chain:
            h = self.health.setdefault(proxy_id, _ProxyHealth())
            if h.is_alive(now):
                return ProxyHandle(
                    proxy_url=proxy_url,
                    proxy_id=proxy_id,
                    matched_rule_index=route.matched_rule_index,
                )

        if route.proxy_required:
            return None
        return ProxyHandle(
            proxy_url=None,
            proxy_id="direct",
            matched_rule_index=route.matched_rule_index,
        )

    def report(self, handle: ProxyHandle, *, success: bool) -> None:
        if handle.proxy_id == "direct":
            return
        h = self.health.setdefault(handle.proxy_id, _ProxyHealth())
        if success:
            h.consecutive_failures = 0
            h.quarantined_until = 0.0
            return
        h.consecutive_failures += 1
        if h.consecutive_failures >= _FAILURE_THRESHOLD:
            h.quarantined_until = time.monotonic() + _QUARANTINE_S
