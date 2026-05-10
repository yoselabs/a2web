"""Proxy pool — stateful layer over the pure RoutePolicy.

Tracks per-proxy health (alive | quarantined_until | dead). Three
consecutive failures quarantine for 600s. Health is in-memory only in
v0.1; PR7e will add disk persistence.

Lifecycle: lazy via `state.ensure_proxy_pool`. No background tasks (no
health-check loop in PR7d — added in PR7e). atexit close is a no-op
today but symmetric with the other pools.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .policy import ResolvedRoute, resolve_route

if TYPE_CHECKING:
    from ..settings import AppSettings


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
    """What a tier sees: the URL to use, the id to record, and pool ref for report()."""

    proxy_url: str | None
    proxy_id: str  # "direct" when proxy_url is None
    matched_rule_index: int | None


@dataclass(slots=True)
class ProxyPool:
    settings: AppSettings
    health: dict[str, _ProxyHealth] = field(default_factory=dict)

    async def close(self) -> None:
        """No-op today; symmetric with sqlite/browser pools."""
        return None

    def resolve(self, host: str, tier: str) -> ResolvedRoute:
        return resolve_route(host, tier, self.settings)

    def acquire(self, host: str, tier: str) -> ProxyHandle | None:
        """Walk primary + fallbacks; return first healthy or direct.

        Returns None when all proxies in the chain are unhealthy AND
        proxy_required is set.
        """
        route = self.resolve(host, tier)
        if route.proxy_id == "direct" or route.proxy_url is None:
            # Explicit-direct or no rule match → direct, never None.
            return ProxyHandle(
                proxy_url=None,
                proxy_id="direct",
                matched_rule_index=route.matched_rule_index,
            )

        chain: list[tuple[str, str]] = []
        # Primary first.
        chain.append((route.proxy_id or "", route.proxy_url))
        # Fallbacks (resolve URLs from settings).
        for fb_id in route.fallback:
            entry = self.settings.proxies.get(fb_id)
            if entry is None:
                continue
            from .policy import _resolve_env  # type: ignore[attr-defined]
            chain.append((fb_id, _resolve_env(entry.url)))

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
        # Soft fallback to direct.
        return ProxyHandle(
            proxy_url=None,
            proxy_id="direct",
            matched_rule_index=route.matched_rule_index,
        )

    def report(self, handle: ProxyHandle, *, success: bool, ms: int) -> None:
        del ms  # reserved for future per-proxy latency tracking
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


__all__ = ["ProxyHandle", "ProxyPool"]
