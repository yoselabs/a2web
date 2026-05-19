"""cookie_store — pure browser-cookie extraction package.

Hand-written readers for Chrome (macOS) and Firefox. No third-party cookie
library; only `cryptography` for the AES-GCM decrypt. No imports from
`a2web.<domain>` — boundary types live in `.models`, domain wiring lives at
the a2web seam (`a2web.cookie_jar`).
"""

from __future__ import annotations

from typing import Literal

from .models import ChromeCookieAccessError, CookieRow


def read_cookies(browser: Literal["chrome", "firefox"], profile: str) -> list[CookieRow]:
    """Dispatch to the per-browser reader.

    Raises `ChromeCookieAccessError` (the Chrome reader's branded exception)
    for missing-profile / missing-sqlite cases regardless of browser. The
    name is historical; treat it as the package's generic access error.
    """
    if browser == "chrome":
        from .chrome import read_cookies as _read

        return _read(profile)
    if browser == "firefox":
        from .firefox import read_cookies as _read

        return _read(profile)
    msg = f"Unsupported browser: {browser!r}"
    raise ValueError(msg)


__all__ = ("ChromeCookieAccessError", "CookieRow", "read_cookies")
