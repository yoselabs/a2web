"""HabrHandler manifest."""

from __future__ import annotations

from plugin_surface import PluginManifest, Unavailable

from a2web.handlers import Handler
from a2web.handlers.habr import HabrHandler
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Handler | Unavailable:
    return HabrHandler()


MANIFEST = PluginManifest(
    name="habr",
    protocol=Handler,
    factory=_build,
    priority=20,
)
