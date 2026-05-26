"""TwitterHandler manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.handlers import Handler
from a2web.handlers.twitter import TwitterHandler
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Handler | Unavailable:
    return TwitterHandler()


MANIFEST = PluginManifest(
    name="twitter",
    protocol=Handler,
    factory=_build,
    priority=40,
)
