"""Route policy — pure resolution from (host, tier, routes, proxies) → decision.

Boundary inputs are Protocol-shaped: any object with the right attribute
shape works. pydantic models, dataclasses, hand-rolled classes — all
fine, no conversion needed at the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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
    """First-match-wins; returns direct (proxy_url=None) when no rule matches.

    Rule semantics:
    - `host`: None or "" matches any host; otherwise exact or `*.glob`
    - `tier`: None or "" matches any tier; otherwise exact tier name
    - Composable AND: a rule with both keys must match both
    - `proxy = "direct"` is an explicit override (matched but no proxy)
    """
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
