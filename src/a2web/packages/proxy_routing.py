"""Proxy routing — pure resolution + stateful pool, in-tree microsofware.

Zero a2web-domain imports. Boundary input is Protocol-shaped — any
duck-typed entry/rule with the right attributes satisfies it.

Two layers:
- `resolve_route` — pure, given routes + proxies, returns a decision
  (proxy_url, fallbacks, required-flag).
- `ProxyPool` — stateful (per-proxy health, quarantine on consecutive
  failures) wrapper over the policy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_QUARANTINE_S = 600.0
_FAILURE_THRESHOLD = 3


# --------------------------------------------------------------------- #
# Protocol-shaped boundary inputs
# --------------------------------------------------------------------- #


@runtime_checkable
class ProxyEntryShape(Protocol):
    """Minimal proxy entry interface the policy reads."""

    url: str


@runtime_checkable
class RouteRuleShape(Protocol):
    """Minimal route rule interface the policy reads."""

    host: str | None
    tier: str | None
    proxy: str
    proxy_required: bool
    fallback: list[str]


# --------------------------------------------------------------------- #
# Policy (pure)
# --------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class ResolvedRoute:
    """Outcome of resolving (host, tier) against the route table."""

    proxy_url: str | None
    proxy_id: str | None
    proxy_required: bool
    fallback: tuple[str, ...]
    matched_rule_index: int | None


def _host_matches(pattern: str, host: str) -> bool:
    """Exact or `*.glob` match (case-insensitive)."""
    p = pattern.lower()
    h = host.lower()
    if p == h:
        return True
    if p.startswith("*."):
        suffix = p[2:]
        return h == suffix or h.endswith("." + suffix)
    if p == "*":
        return True
    return False


def resolve_route(
    host: str,
    tier: str,
    *,
    routes: list[RouteRuleShape],
    proxies: dict[str, ProxyEntryShape],
) -> ResolvedRoute:
    """First-match-wins; returns direct (proxy_url=None) when no rule matches."""
    for idx, rule in enumerate(routes):
        rule_host = rule.host or ""
        rule_tier = rule.tier or ""
        if rule_host and not _host_matches(rule_host, host):
            continue
        if rule_tier and rule_tier != tier:
            continue
        if rule.proxy == "direct":
            return ResolvedRoute(
                proxy_url=None,
                proxy_id="direct",
                proxy_required=False,
                fallback=(),
                matched_rule_index=idx,
            )
        proxy_entry = proxies.get(rule.proxy)
        if proxy_entry is None:
            return ResolvedRoute(
                proxy_url=None,
                proxy_id=None,
                proxy_required=False,
                fallback=(),
                matched_rule_index=idx,
            )
        return ResolvedRoute(
            proxy_url=proxy_entry.url,
            proxy_id=rule.proxy,
            proxy_required=rule.proxy_required,
            fallback=tuple(rule.fallback),
            matched_rule_index=idx,
        )
    return ResolvedRoute(
        proxy_url=None,
        proxy_id=None,
        proxy_required=False,
        fallback=(),
        matched_rule_index=None,
    )


# --------------------------------------------------------------------- #
# Stateful pool
# --------------------------------------------------------------------- #


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
    """Stateful proxy pool keyed off a route table + proxies map."""

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


__all__ = (
    "ProxyEntryShape",
    "ProxyHandle",
    "ProxyPool",
    "ResolvedRoute",
    "RouteRuleShape",
    "resolve_route",
)
