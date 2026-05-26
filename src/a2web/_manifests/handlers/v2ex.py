"""V2EXHandler manifest."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.handlers import Handler
from a2web.handlers.v2ex import V2EXHandler
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Handler | Unavailable:
    return V2EXHandler()


MANIFEST = PluginManifest(
    name="v2ex",
    protocol=Handler,
    factory=_build,
    priority=10,
)
