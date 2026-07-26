"""WikipediaHandler manifest."""

from __future__ import annotations

from plugin_surface import PluginManifest, Unavailable

from a2web.handlers import Handler
from a2web.handlers.wikipedia import WikipediaHandler
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Handler | Unavailable:
    return WikipediaHandler()


MANIFEST = PluginManifest(
    name="wikipedia",
    protocol=Handler,
    factory=_build,
    priority=60,
)
