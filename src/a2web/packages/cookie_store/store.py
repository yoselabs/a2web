"""browser-cookie3 adapter — single dispatch for all supported browsers.

Replaces the previous hand-rolled `chrome.py` / `firefox.py` readers (v0.8 →
v0.16). browser-cookie3 owns the per-browser file paths, decryption (Chrome
AES-GCM via pycryptodomex + Keychain on macOS), and the OS matrix
(macOS / Linux / Windows). This module narrows it to a typed boundary:
`CookieSource` literal → `list[CookieRow]`.

Per-browser `profile` resolution defers to browser-cookie3 defaults when
`profile == "Default"`. A non-default `profile` value is currently a hint
only — browser-cookie3 does not expose per-profile selection uniformly
across browsers; expand here when a concrete need arrives.

NEVER include cookie values, AES keys, or Keychain material in raised
exception messages. `CookieAccessError` carries structural context only
(browser name, exception class). `__cause__` preserves the original.
"""

from __future__ import annotations

from http.cookiejar import Cookie, CookieJar
from typing import Literal

from .models import CookieRow, SameSite

CookieSource = Literal[
    "chrome",
    "chromium",
    "brave",
    "edge",
    "firefox",
    "safari",
    "vivaldi",
    "opera",
    "opera_gx",
]


class CookieAccessError(RuntimeError):
    """Raised when a browser's cookie store cannot be read or decrypted.

    The message NEVER contains cookie values or key material — only the
    browser name and the upstream exception class. `__cause__` is the
    original exception.
    """


def _dispatch(source: CookieSource):
    import browser_cookie3 as bc3

    table = {
        "chrome": bc3.chrome,
        "chromium": bc3.chromium,
        "brave": bc3.brave,
        "edge": bc3.edge,
        "firefox": bc3.firefox,
        "safari": bc3.safari,
        "vivaldi": bc3.vivaldi,
        "opera": bc3.opera,
        "opera_gx": bc3.opera_gx,
    }
    try:
        return table[source]
    except KeyError as err:
        msg = f"Unsupported cookie source: {source!r}"
        raise CookieAccessError(msg) from err


def _samesite(cookie: Cookie) -> SameSite:
    raw = cookie.get_nonstandard_attr("SameSite") or cookie.get_nonstandard_attr("samesite")
    if raw is None:
        return None
    s = str(raw).lower()
    if s == "lax":
        return "lax"
    if s == "strict":
        return "strict"
    if s == "none":
        return "none"
    return None


def _to_row(cookie: Cookie) -> CookieRow:
    # `http.cookiejar.Cookie.domain` is the on-disk host_key shape: either
    # bare host or leading-dot domain-match form. Pass through unchanged.
    expires = int(cookie.expires) if cookie.expires else None
    is_secure = 1 if cookie.secure else 0
    is_httponly = 1 if cookie.has_nonstandard_attr("HttpOnly") else 0
    return CookieRow(
        host_key=cookie.domain or "",
        name=cookie.name or "",
        value=cookie.value or "",
        path=cookie.path or "/",
        expires_utc=expires,
        is_secure=is_secure,
        is_httponly=is_httponly,
        samesite=_samesite(cookie),
    )


def read_cookies(
    source: CookieSource,
    profile: str | None = None,
    domain: str | None = None,
) -> list[CookieRow]:
    """Read all cookies from the given browser's default profile.

    `profile` is currently unused (reserved for a future per-browser
    profile-file resolver); browser-cookie3 selects the system default.
    `domain` narrows extraction at the source when provided.
    """
    fn = _dispatch(source)
    try:
        jar: CookieJar = fn(domain_name=domain or "")
    except CookieAccessError:
        raise
    except Exception as err:
        msg = f"Failed to read {source} cookies ({type(err).__name__})"
        raise CookieAccessError(msg) from err
    return [_to_row(c) for c in jar]


__all__ = ("CookieAccessError", "CookieSource", "read_cookies")
