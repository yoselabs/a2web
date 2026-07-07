"""Patchright backend manifest — the fast Chromium rung (`browser` tier).

`PlaywrightBackend` over the Patchright launcher; surfaces `Unavailable` when
Patchright is absent so the registry drops it cleanly. Kept engine after the
bake-off (fast rung); the robust rung is `zendriver`.
"""

from __future__ import annotations

import importlib.util

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.browser_backends import BrowserBackend, PlaywrightBackend, patchright_launcher
from a2web.settings import AppSettings
from a2web.state import _emit_browser_stderr


def _build(settings: AppSettings) -> BrowserBackend | Unavailable:
    if importlib.util.find_spec("patchright") is None:
        return Unavailable("patchright not installed")
    return PlaywrightBackend(
        patchright_launcher,
        name="patchright",
        max_pool=settings.browser_max_pool,
        idle_timeout_s=settings.browser_idle_timeout_s,
        page_budget_s=settings.browser_page_budget_s,
        launch_budget_s=settings.browser_launch_budget_s,
        reaper_interval_s=settings.browser_reaper_interval_s,
        stderr_sink=_emit_browser_stderr,
    )


MANIFEST = PluginManifest(name="patchright", protocol=BrowserBackend, factory=_build, requires=())
