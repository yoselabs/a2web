"""Route policy — pure resolution from settings + (host, tier) → decision.

No I/O, no mutable state. The orchestrator calls `resolve_route` once
per tier invocation; `ProxyPool` adds the stateful (health, quarantine)
layer on top.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings import AppSettings


@dataclass(slots=True, frozen=True)
class ResolvedRoute:
    """Outcome of resolving (host, tier) against the route table."""

    proxy_url: str | None
    proxy_id: str | None
    proxy_required: bool
    fallback: tuple[str, ...]
    matched_rule_index: int | None


_ENV_REF_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _resolve_env(url: str) -> str:
    """Replace `${VAR}` with `os.environ[VAR]`; leave literal on miss."""

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return _ENV_REF_RE.sub(_sub, url)


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


def resolve_route(host: str, tier: str, settings: AppSettings) -> ResolvedRoute:
    """First-match-wins; returns direct (proxy_url=None) when no rule matches.

    Rule semantics:
    - `host`: None or "" matches any host; otherwise exact or `*.glob`
    - `tier`: None or "" matches any tier; otherwise exact tier name
    - Composable AND: a rule with both keys must match both
    - `proxy = "direct"` is an explicit override (matched but no proxy)
    """
    for idx, rule in enumerate(settings.routes):
        rule_host = rule.host or ""
        rule_tier = rule.tier or ""
        if rule_host and not _host_matches(rule_host, host):
            continue
        if rule_tier and rule_tier != tier:
            continue
        # Match.
        if rule.proxy == "direct":
            return ResolvedRoute(
                proxy_url=None,
                proxy_id="direct",
                proxy_required=False,
                fallback=(),
                matched_rule_index=idx,
            )
        proxy_entry = settings.proxies.get(rule.proxy)
        if proxy_entry is None:
            # Rule names a proxy that doesn't exist; treat as direct.
            return ResolvedRoute(
                proxy_url=None,
                proxy_id=None,
                proxy_required=False,
                fallback=(),
                matched_rule_index=idx,
            )
        return ResolvedRoute(
            proxy_url=_resolve_env(proxy_entry.url),
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


__all__ = ["ResolvedRoute", "resolve_route"]
