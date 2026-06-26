"""Camoufox backend manifest — `PlaywrightBackend` with the Camoufox launcher.

Always registers; the optional `[browser]` extra is checked lazily at launch
(a missing dep surfaces as `RenderOutcome.unavailable` at render time, mapped
to a `browser_unavailable` hint by the tier).
"""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.browser_backends import BrowserBackend, PlaywrightBackend, camoufox_launcher
from a2web.settings import AppSettings
from a2web.state import _emit_browser_stderr


def _build(settings: AppSettings) -> BrowserBackend | Unavailable:
    return PlaywrightBackend(
        camoufox_launcher,
        name="camoufox",
        max_pool=settings.browser_max_pool,
        idle_timeout_s=settings.browser_idle_timeout_s,
        page_budget_s=settings.browser_page_budget_s,
        stderr_sink=_emit_browser_stderr,
    )


MANIFEST = PluginManifest(name="camoufox", protocol=BrowserBackend, factory=_build, requires=())
