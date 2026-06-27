"""Patchright launcher — Chromium Playwright drop-in (bake-off candidate).

TRANSIENT (browser-backend-bakeoff): one of three candidate engines. Patchright
is an undetected Playwright fork that vendors its own playwright-core and browser
binary; only the launch differs from Camoufox, so it reuses `PlaywrightBackend`
wholesale via a `launch_fn`. Deleted if it loses the bake-off; promoted to a
baseline dep if it wins.
"""

from __future__ import annotations

from typing import Any

from .playwright import chromium_launch


def patchright_launcher() -> Any:
    """Yield an async-CM launching headless Chromium via Patchright. ImportError
    (no `bakeoff` extra) propagates → the backend reports `unavailable`."""
    from patchright.async_api import async_playwright

    return chromium_launch(async_playwright)
