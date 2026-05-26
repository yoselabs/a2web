"""Test fixture — minimal plugin module declaring a MANIFEST."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings


@runtime_checkable
class Widget(Protocol):
    name: str


class AlphaWidget:
    name = "alpha"


def _build(_settings: AppSettings) -> Widget | Unavailable:
    return AlphaWidget()


MANIFEST = PluginManifest(
    name="alpha",
    protocol=Widget,
    factory=_build,
)
