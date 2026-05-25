"""Boundary types for the cookie_store package.

Package-owned types — no imports from `a2web.<domain>`. The domain wires its
own `Cookie` shape (in `a2web.cookie_jar`) and converts from `CookieRow` at
the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SameSite = Literal["lax", "strict", "none"] | None


@dataclass(slots=True, frozen=True)
class CookieRow:
    """One cookie as returned by the per-browser reader.

    Storage shape is normalized across Chrome and Firefox. Domain code
    converts to its own `Cookie` shape when bridging into `CookieJarResource`.

    - `host_key`: Chrome-style — either `example.com` (host-only) or
      `.example.com` (domain match).
    - `expires_utc`: unix seconds. `None` means session cookie (no expiry).
    - `is_secure`, `is_httponly`: ints (0/1) to match the on-disk sqlite shape.
    """

    host_key: str
    name: str
    value: str
    path: str
    expires_utc: int | None
    is_secure: int
    is_httponly: int
    samesite: SameSite


class ChromeCookieAccessError(RuntimeError):
    """Raised when Chrome cookies cannot be read or decrypted.

    Covers missing profile dir, missing sqlite file, Keychain access denied,
    `security` CLI failures, decryption errors. The message NEVER contains
    decrypted cookie values or the AES key — only structural context (paths,
    exit codes, error class).
    """


__all__ = ("ChromeCookieAccessError", "CookieRow", "SameSite")
