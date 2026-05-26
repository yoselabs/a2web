"""RawTier manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.raw import RawTier


def _build(_settings: AppSettings) -> Tier | Unavailable:
    return RawTier()


MANIFEST = PluginManifest(
    name="raw",
    protocol=Tier,
    factory=_build,
    priority=20,
)
