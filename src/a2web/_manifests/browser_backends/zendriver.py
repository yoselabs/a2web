"""Zendriver backend manifest — the CDP candidate (`ZendriverBackend`).

TRANSIENT (browser-backend-bakeoff): bake-off candidate. Surfaces `Unavailable`
when the `bakeoff` extra is absent so the registry drops it cleanly. Unlike the
Playwright-family manifests it builds a `ZendriverBackend` (CDP), not a
`PlaywrightBackend`. No `stderr_sink`: zendriver drives Chromium over CDP
in-process, not via a Node driver subprocess, so there's no inherited stderr to
capture. Removed if it loses the bake-off.
"""

from __future__ import annotations

import importlib.util

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.browser_backends import BrowserBackend, ZendriverBackend
from a2web.settings import AppSettings


def _build(settings: AppSettings) -> BrowserBackend | Unavailable:
    if importlib.util.find_spec("zendriver") is None:
        return Unavailable("zendriver not installed (install the [browser] extra)")
    return ZendriverBackend(name="zendriver", page_budget_s=settings.browser_page_budget_s)


MANIFEST = PluginManifest(name="zendriver", protocol=BrowserBackend, factory=_build, requires=())
