"""a2web seam — route policy over `packages.proxy_routing`.

Public surface: `resolve_route(host, tier, settings)`. Forwards
`settings.routes` / `settings.proxies` (pydantic models) into the
package; the package reads them via Protocol-shaped boundary types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ..packages.proxy_routing import (
    ProxyEntryShape,
    ResolvedRoute,
    RouteRuleShape,
)
from ..packages.proxy_routing import (
    resolve_route as _package_resolve_route,
)

if TYPE_CHECKING:
    from ..settings import AppSettings

__all__ = ("ResolvedRoute", "resolve_route")


def resolve_route(host: str, tier: str, settings: AppSettings) -> ResolvedRoute:
    """First-match-wins; returns direct when no rule matches."""
    return _package_resolve_route(
        host,
        tier,
        routes=cast("list[RouteRuleShape]", settings.routes),
        proxies=cast("dict[str, ProxyEntryShape]", settings.proxies),
    )
