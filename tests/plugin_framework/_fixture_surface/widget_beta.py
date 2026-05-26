"""Test fixture — second plugin."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings

from .widget_alpha import Widget


class BetaWidget:
    name = "beta"


def _build(_settings: AppSettings) -> Widget | Unavailable:
    return BetaWidget()


MANIFEST = PluginManifest(name="beta", protocol=Widget, factory=_build)
