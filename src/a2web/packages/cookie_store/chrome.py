"""Chrome cookie reader — macOS-only in v0.8.

Three concerns:

1. Locate the Cookies sqlite under
   `~/Library/Application Support/Google/Chrome/<profile>/Cookies` and copy
   it to a tempdir to dodge contention with a running Chrome.
2. Fetch the AES key from the Keychain via the OS `security` CLI. macOS
   pops a prompt the first time a new binary asks; subsequent runs follow
   the per-user ACL. We shell out rather than link against Security.framework
   because the binary is universally present and the surface is tiny.
3. PBKDF2-HMAC-SHA1 the key with salt `b"saltysalt"` and 1003 iterations,
   then AES-GCM-decrypt each `encrypted_value` prefixed with `v10`/`v11`.

The reader returns plaintext values as-is when `encrypted_value` is empty
(legacy unencrypted rows). It NEVER includes decrypted material or the AES
key in any exception message — see `ChromeCookieAccessError`.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .models import ChromeCookieAccessError, CookieRow, SameSite

_KEYCHAIN_ITEM = "Chrome Safe Storage"
_PBKDF2_SALT = b"saltysalt"
_PBKDF2_ITERATIONS = 1003  # macOS-specific (Linux uses 1)
_AES_KEY_BYTES = 16
# Chrome on macOS uses an all-spaces IV. The constant is part of the
# documented encryption envelope (see Chromium `os_crypt_mac.mm`).
_AES_GCM_IV = b" " * 12


def _profile_dir(profile: str) -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / profile


def _cookies_path(profile: str) -> Path:
    return _profile_dir(profile) / "Cookies"


def _fetch_keychain_key() -> str:
    """Run `security find-generic-password -wa "Chrome Safe Storage"`.

    Returns the keychain password (the user-visible "service password" — a
    base64 blob in practice). Raises `ChromeCookieAccessError` with NO secret
    material on any non-zero exit (user denied, keychain locked, item not
    found, etc.).
    """
    try:
        proc = subprocess.run(  # noqa: S603
            ["/usr/bin/security", "find-generic-password", "-wa", _KEYCHAIN_ITEM],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        msg = "/usr/bin/security not found — not a macOS host?"
        raise ChromeCookieAccessError(msg) from exc

    if proc.returncode != 0:
        msg = (
            f"`security find-generic-password` exited {proc.returncode} for "
            f"item {_KEYCHAIN_ITEM!r}. The user may have denied the prompt, "
            "the keychain may be locked, or the item may be missing."
        )
        raise ChromeCookieAccessError(msg)
    return proc.stdout.rstrip("\n")


def _derive_aes_key(password: str) -> bytes:
    """PBKDF2-HMAC-SHA1, salt `saltysalt`, 1003 iters, 16-byte key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),  # noqa: S303 (documented Chrome envelope)
        length=_AES_KEY_BYTES,
        salt=_PBKDF2_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _decrypt_value(encrypted: bytes, key: bytes) -> str:
    """Decrypt a Chrome v10/v11 encrypted_value blob; pass empty through."""
    if not encrypted:
        return ""
    # Chrome envelopes: `v10` (older macOS) and `v11` (newer). Both use
    # AES-GCM on macOS today; the prefix is a versioning hint not a cipher
    # selector for our case.
    if encrypted[:3] in (b"v10", b"v11"):
        ciphertext = encrypted[3:]
    else:
        # Pre-v10 was AES-CBC; not seen on macOS for years. Treat as bad
        # input rather than silently producing junk.
        msg = "encrypted_value missing v10/v11 prefix — pre-AES-GCM envelope (AES-CBC) not supported in v0.8"
        raise ChromeCookieAccessError(msg)
    try:
        return AESGCM(key).decrypt(_AES_GCM_IV, ciphertext, None).decode("utf-8")
    except Exception as exc:
        msg = f"AES-GCM decrypt failed ({type(exc).__name__}); cookie skipped"
        raise ChromeCookieAccessError(msg) from None


def _samesite_from_int(value: int | None) -> SameSite:
    """Chromium `same_site`: -1=unset|0=none|1=lax|2=strict."""
    if value is None or value < 0:
        return None
    if value == 1:
        return "lax"
    if value == 2:
        return "strict"
    if value == 0:
        return "none"
    return None


def read_cookies(profile: str) -> list[CookieRow]:
    """Read + decrypt all cookies for a Chrome profile."""
    pdir = _profile_dir(profile)
    if not pdir.is_dir():
        msg = f"Chrome profile not found at {pdir}"
        raise ChromeCookieAccessError(msg)
    src = _cookies_path(profile)
    if not src.is_file():
        msg = f"Chrome Cookies sqlite missing under {pdir}"
        raise ChromeCookieAccessError(msg)

    password = _fetch_keychain_key()
    key = _derive_aes_key(password)

    with tempfile.TemporaryDirectory(prefix="a2web-chrome-cookies-") as td:
        dst = Path(td) / "Cookies"
        shutil.copy2(src, dst)
        # Some Chrome installs ship WAL/SHM siblings; copy them when present
        # so the snapshot is consistent.
        for suffix in ("-wal", "-shm"):
            sibling = src.with_name(src.name + suffix)
            if sibling.is_file():
                shutil.copy2(sibling, dst.with_name(dst.name + suffix))
        conn = sqlite3.connect(str(dst))
        try:
            cursor = conn.execute(
                "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite FROM cookies",
            )
            raw_rows = cursor.fetchall()
        finally:
            conn.close()

    # Chrome stores `expires_utc` as microseconds since 1601-01-01 (Windows
    # FILETIME / Chromium time). Convert to unix seconds; 0 means session.
    _EPOCH_DELTA_S = 11_644_473_600
    out: list[CookieRow] = []
    for host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite in raw_rows:
        if encrypted_value:
            try:
                plaintext = _decrypt_value(encrypted_value, key)
            except ChromeCookieAccessError:
                # Skip individual undecryptable rows rather than failing the
                # whole refresh — a single broken row shouldn't poison the
                # entire mirror.
                continue
        else:
            plaintext = value or ""
        if expires_utc and int(expires_utc) > 0:
            exp_unix: int | None = int(int(expires_utc) / 1_000_000) - _EPOCH_DELTA_S
        else:
            exp_unix = None
        out.append(
            CookieRow(
                host_key=host_key or "",
                name=name or "",
                value=plaintext,
                path=path or "/",
                expires_utc=exp_unix,
                is_secure=1 if is_secure else 0,
                is_httponly=1 if is_httponly else 0,
                samesite=_samesite_from_int(samesite),
            ),
        )
    return out


__all__ = ("read_cookies",)
