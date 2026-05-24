"""cookie_store — browser cookie extraction package.

Thin adapter over `browser-cookie3` (v0.16+). Cross-platform
(macOS / Linux / Windows) and multi-browser (Chrome / Chromium / Brave /
Edge / Firefox / Safari / Vivaldi / Opera / Opera GX). The package owns the
boundary types in `.models` and the dispatch in `.store`; domain wiring
lives at the a2web seam (`a2web.cookie_jar`). No imports from
`a2web.<domain>` — invariant enforced by `tests/test_packages_independence.py`.

`ChromeCookieAccessError` is re-exported as a historical alias of
`CookieAccessError` for any external caller pinned to the v0.8 name.
"""

from __future__ import annotations

from .models import ChromeCookieAccessError, CookieRow
from .store import CookieAccessError, CookieSource, read_cookies

__all__ = (
    "ChromeCookieAccessError",
    "CookieAccessError",
    "CookieRow",
    "CookieSource",
    "read_cookies",
)
