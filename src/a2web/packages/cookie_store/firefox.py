"""Firefox cookie reader — `cookies.sqlite` is plaintext, no decryption.

Resolves a profile name (full directory name or `default-release`/`default`
alias), copies the sqlite file to a tempdir to dodge any lock contention,
reads `moz_cookies`, and normalizes rows into the package's `CookieRow`
shape.

macOS-first: profile root is `~/Library/Application Support/Firefox/Profiles/`.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from .models import ChromeCookieAccessError, CookieRow, SameSite


def _profiles_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"


def _resolve_profile_dir(profile: str) -> Path:
    """Return the on-disk profile directory.

    Accepts either a literal directory name (e.g. `xxxxxxxx.default-release`)
    or a channel alias (`default-release` / `default`); when an alias is
    given, the lexically-first matching directory is selected.
    """
    root = _profiles_root()
    if not root.is_dir():
        msg = f"Firefox profiles directory not found at {root}"
        raise ChromeCookieAccessError(msg)
    direct = root / profile
    if direct.is_dir():
        return direct
    matches = sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith("." + profile))
    if not matches:
        msg = f"Firefox profile not found: {profile} (under {root})"
        raise ChromeCookieAccessError(msg)
    return matches[0]


def _samesite_from_int(value: int | None) -> SameSite:
    """Firefox `sameSite` is 0|1|2 (none|lax|strict)."""
    if value is None:
        return None
    if value == 1:
        return "lax"
    if value == 2:
        return "strict"
    if value == 0:
        return "none"
    return None


def read_cookies(profile: str) -> list[CookieRow]:
    """Read all rows from the Firefox cookie store and normalize them."""
    pdir = _resolve_profile_dir(profile)
    src = pdir / "cookies.sqlite"
    if not src.is_file():
        msg = f"Firefox cookies.sqlite missing under {pdir}"
        raise ChromeCookieAccessError(msg)

    with tempfile.TemporaryDirectory(prefix="a2web-firefox-cookies-") as td:
        dst = Path(td) / "cookies.sqlite"
        shutil.copy2(src, dst)
        conn = sqlite3.connect(str(dst))
        try:
            cursor = conn.execute(
                "SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite FROM moz_cookies",
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

    out: list[CookieRow] = []
    for host, name, value, path, expiry, is_secure, is_httponly, samesite in rows:
        # Firefox stores host without leading dot for host-only cookies and
        # with a leading dot for domain matches. That already matches the
        # Chrome `host_key` convention — pass through.
        out.append(
            CookieRow(
                host_key=host or "",
                name=name or "",
                value=value or "",
                path=path or "/",
                # Firefox stores 0 for session cookies; map to None.
                expires_utc=int(expiry) if expiry else None,
                is_secure=1 if is_secure else 0,
                is_httponly=1 if is_httponly else 0,
                samesite=_samesite_from_int(samesite),
            ),
        )
    return out


__all__ = ("read_cookies",)
