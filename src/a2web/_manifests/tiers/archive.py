"""ArchiveTier manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.archive import ArchiveTier


def _build(_settings: AppSettings) -> Tier | Unavailable:
    return ArchiveTier()


MANIFEST = PluginManifest(
    name="archive",
    protocol=Tier,
    factory=_build,
    priority=-1,
)
