"""Zendriver backend manifest — the CDP candidate (`ZendriverBackend`).

The robust rung (`browser_robust` tier), kept permanently by the
`browser-backend-bakeoff` alongside patchright's fast rung. Surfaces
`Unavailable` when the `[browser]` extra is absent so the registry drops it
cleanly — note that is the `[browser]` extra, not the `bakeoff` extra this
docstring used to name; the bake-off extra was deleted when both survivors
were promoted out of it. Unlike the Playwright-family manifests it builds a
`ZendriverBackend` (CDP), not a `PlaywrightBackend`.

No `stderr_sink` — but NOT for the reason previously recorded here. This module
used to claim zendriver "drives Chromium over CDP in-process ... so there's no
inherited stderr to capture". That is wrong: zendriver spawns Chromium as a real
child process, which writes to stderr like any other. The consequence of
believing otherwise was that every containerized launch failure surfaced as
zendriver's opaque "Failed to connect to browser" with no cause attached, and
the robust rung stayed broken in the published image without anyone seeing why.
The backend now probes the resolved binary itself and attaches the output to
`RenderedPage.detail` (`zendriver._launch_diagnostics`), which keeps the
diagnosis at the layer that owns the launch rather than routing a child's
stderr through the manifest.
"""

from __future__ import annotations

import importlib.util

from plugin_surface import PluginManifest, Unavailable

from a2web.packages.browser_backends import BrowserBackend, ZendriverBackend
from a2web.settings import AppSettings


def _build(settings: AppSettings) -> BrowserBackend | Unavailable:
    if importlib.util.find_spec("zendriver") is None:
        return Unavailable("zendriver not installed (install the [browser] extra)")
    return ZendriverBackend(name="zendriver", page_budget_s=settings.browser_page_budget_s)


MANIFEST = PluginManifest(name="zendriver", protocol=BrowserBackend, factory=_build, requires=())
