"""JinaTier manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.jina import JinaTier


def _build(_settings: AppSettings) -> Tier | Unavailable:
    return JinaTier()


MANIFEST = PluginManifest(
    name="jina",
    protocol=Tier,
    factory=_build,
    priority=10,
)
