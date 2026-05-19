"""AES-GCM round-trip test for the Chrome cookie envelope.

Never touches real Chrome or the Keychain — we hand-craft the same envelope
that Chrome produces (`v10` || AES-GCM(plaintext)) using the same key
derivation (PBKDF2-HMAC-SHA1, salt `saltysalt`, 1003 iterations) and assert
the package decrypt path round-trips.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from a2web.packages.cookie_store.chrome import (
    _AES_GCM_IV,
    _decrypt_value,
    _derive_aes_key,
)
from a2web.packages.cookie_store.models import ChromeCookieAccessError


def _encrypt(plaintext: str, password: str) -> bytes:
    """Produce a Chrome-v10-shaped encrypted_value blob."""
    key = _derive_aes_key(password)
    ct = AESGCM(key).encrypt(_AES_GCM_IV, plaintext.encode("utf-8"), None)
    return b"v10" + ct


def test_round_trip_simple() -> None:
    password = "test-password"
    plaintext = "session=abc123"
    blob = _encrypt(plaintext, password)
    key = _derive_aes_key(password)
    assert _decrypt_value(blob, key) == plaintext


def test_round_trip_unicode() -> None:
    password = "p@ssword!"
    plaintext = "name=Денис; emoji=🍪"
    blob = _encrypt(plaintext, password)
    key = _derive_aes_key(password)
    assert _decrypt_value(blob, key) == plaintext


def test_empty_value_returns_empty() -> None:
    assert _decrypt_value(b"", _derive_aes_key("anything")) == ""


def test_missing_prefix_raises() -> None:
    key = _derive_aes_key("x")
    with pytest.raises(ChromeCookieAccessError):
        _decrypt_value(b"\x00\x01raw-aes-cbc-bytes", key)


def test_wrong_key_raises() -> None:
    blob = _encrypt("hi", "right")
    wrong = _derive_aes_key("wrong")
    with pytest.raises(ChromeCookieAccessError):
        _decrypt_value(blob, wrong)
