"""Patchright launcher — Chromium Playwright drop-in, the FAST rung.

**Kept engine, and permanent.** The `browser-backend-bakeoff` (archived
2026-06-27) kept two engines: patchright drives the `browser` tier and
zendriver the `browser_robust` escalation. `rebrowser` lost and was deleted.

Patchright is an undetected Playwright fork that vendors its own
playwright-core and browser binary; only the launch differs from Camoufox, so
it reuses `PlaywrightBackend` wholesale via a `launch_fn`. Shipped in the
`[browser]` extra (not baseline — the baked Chromium dominates image size and
the tier is escalation-only).
"""

from __future__ import annotations

from typing import Any

from .playwright import chromium_launch


def patchright_launcher() -> Any:
    """Yield an async-CM launching headless Chromium via Patchright. ImportError
    (no `[browser]` extra) propagates → the backend reports `unavailable`."""
    from patchright.async_api import async_playwright

    return chromium_launch(async_playwright)
