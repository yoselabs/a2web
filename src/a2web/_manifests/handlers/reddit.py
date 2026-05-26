"""RedditHandler manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.handlers import Handler
from a2web.handlers.reddit import RedditHandler
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Handler | Unavailable:
    return RedditHandler()


MANIFEST = PluginManifest(
    name="reddit",
    protocol=Handler,
    factory=_build,
    priority=90,
)
