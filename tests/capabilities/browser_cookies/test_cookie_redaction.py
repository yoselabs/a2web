"""Redaction discipline — cookie values never appear in observability output.

Covers the helper directly (`redact_cookie_for_event`) and the
`CookiesAttached` LDD event emission path (which uses cookie *names* but
NOT values).
"""

from __future__ import annotations

from a2web.cookie_jar import Cookie, redact_cookie_for_event
from a2web.events.types import CookiesAttached


def _cookie(name: str = "sid", value: str = "supersecret") -> Cookie:
    return Cookie(
        name=name,
        value=value,
        host_key=".example.com",
        path="/",
        expires_utc=None,
        is_secure=1,
        is_httponly=1,
        samesite="lax",
    )


def test_redact_cookie_for_event_drops_value() -> None:
    c = _cookie(value="supersecret-token-xyz")
    payload = redact_cookie_for_event(c)
    assert "supersecret" not in repr(payload)
    assert "supersecret-token-xyz" not in repr(payload)
    assert payload["name"] == "sid"
    assert payload["host_key"] == ".example.com"
    assert payload["path"] == "/"
    assert payload["value_length"] == len("supersecret-token-xyz")


def test_redact_cookie_payload_keys() -> None:
    payload = redact_cookie_for_event(_cookie())
    assert set(payload.keys()) == {"name", "host_key", "path", "value_length"}
    assert "value" not in payload


def test_cookies_attached_event_carries_names_not_values() -> None:
    """The wire payload — names only, no values anywhere."""
    cookies = [_cookie(name="sid", value="secret-A"), _cookie(name="csrf", value="secret-B")]
    event = CookiesAttached(
        t_ms=100,
        host="example.com",
        cookie_count=len(cookies),
        cookie_names=[c.name for c in cookies],
    )
    blob = repr(event)
    assert "secret-A" not in blob
    assert "secret-B" not in blob
    assert "sid" in blob
    assert "csrf" in blob
