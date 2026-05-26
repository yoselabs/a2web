"""Test fixture — plugin that returns Unavailable, must NOT appear in registry."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings

from .widget_alpha import Widget


def _build(_settings: AppSettings) -> Widget | Unavailable:
    return Unavailable("test: capability missing")


MANIFEST = PluginManifest(name="gamma", protocol=Widget, factory=_build)
