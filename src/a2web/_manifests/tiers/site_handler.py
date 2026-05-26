"""SiteHandlerTier manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.site_handler import SiteHandlerTier


def _build(_settings: AppSettings) -> Tier | Unavailable:
    return SiteHandlerTier()


MANIFEST = PluginManifest(
    name="site_handler",
    protocol=Tier,
    factory=_build,
    priority=30,
)
