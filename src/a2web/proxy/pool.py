"""a2web seam — stateful proxy pool over `packages.proxy_routing`.

Accepts `AppSettings` and forwards `routes` / `proxies` into the
package. Re-exports `ProxyHandle` so existing callers
(`from a2web.proxy.pool import ProxyPool, ProxyHandle`) keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ..packages.proxy_routing import ProxyEntryShape, ProxyHandle, RouteRuleShape
from ..packages.proxy_routing import ProxyPool as _PackageProxyPool

if TYPE_CHECKING:
    from ..settings import AppSettings

__all__ = ("ProxyHandle", "ProxyPool")


class ProxyPool(_PackageProxyPool):
    """a2web seam: accepts `AppSettings`, forwards `routes`/`proxies` to the package."""

    def __init__(self, *, settings: AppSettings) -> None:
        self._settings = settings
        super().__init__(
            routes=cast("list[RouteRuleShape]", settings.routes),
            proxies=cast("dict[str, ProxyEntryShape]", settings.proxies),
        )

    @property
    def settings(self) -> AppSettings:
        """Back-compat accessor for callers that read `.settings` directly."""
        return self._settings
