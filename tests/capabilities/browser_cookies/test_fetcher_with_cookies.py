"""Integration tests for cookies in the fetch pipeline.

Three flows:
- (a) `cookie_source=none` — no cookies, no hint.
- (b) `cookie_source=chrome` with a fresh mirror — raw tier sees cookies dict,
  no `cookies_stale` hint.
- (c) `cookie_source=chrome` with a stale mirror — cookies still flow, AND
  the response has an `OperatorHint(code="cookies_stale", ...)` exactly once.

The cookie_store reader is monkeypatched so no real Chrome / Keychain access
happens. The raw tier's `curl_cffi.AsyncSession` is faked so we can assert
the cookies kwarg without network I/O.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

import pytest
from a2kit.testing import lazy

from a2web.cache import SqliteResource
from a2web.cookie_jar import build_cookie_jar
from a2web.fetcher import fetch
from a2web.packages.cookie_store.models import CookieRow
from a2web.settings import AppSettings
from tests.conftest import make_default_state


def _make_settings(source: str = "chrome", stale_h: int = 24) -> AppSettings:
    return AppSettings(
        cookie_source=source,
        cookie_profile="Default",
        cookie_stale_after_hours=stale_h,
    )


class _FakeResponse:
    headers: ClassVar[dict[str, str]] = {"content-type": "text/html"}
    content = b"<html><head><title>X</title></head><body><article>" + b"<p>" + (b"hello world " * 200) + b"</p></article></body></html>"
    status_code = 200
    url = "https://example.com/"


class _FakeSession:
    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).last_kwargs = kwargs
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _patch_curl(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", _FakeSession)
    _FakeSession.last_kwargs = {}


def _fake_chrome_rows() -> list[CookieRow]:
    return [
        CookieRow(
            host_key=".example.com",
            name="sid",
            value="abc123",
            path="/",
            expires_utc=None,
            is_secure=1,
            is_httponly=1,
            samesite="lax",
        ),
        CookieRow(
            host_key="example.com",
            name="csrf",
            value="xyz789",
            path="/",
            expires_utc=None,
            is_secure=0,
            is_httponly=0,
            samesite=None,
        ),
    ]


async def test_cookie_source_none_no_cookies_no_hint(tmp_path: Path) -> None:
    """Default off — fetch behaves exactly as pre-v0.8."""
    state = make_default_state(_make_settings(source="none"))
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(state.settings, sqlite)
    try:
        response = await fetch("https://example.com/", state=state, cookie_jar=lazy(jar))
        assert "cookies" not in _FakeSession.last_kwargs
        assert not any(h.code == "cookies_stale" for h in response.operator_hints)
    finally:
        await sqlite.close()


async def test_chrome_fresh_mirror_cookies_flow_no_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh mirror — raw tier receives the cookies dict, no stale hint."""
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: _fake_chrome_rows())

    state = make_default_state(_make_settings(source="chrome", stale_h=24))
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(state.settings, sqlite)
    try:
        await jar.refresh()  # just refreshed → fresh
        response = await fetch("https://example.com/", state=state, cookie_jar=lazy(jar))

        cookies_sent = _FakeSession.last_kwargs.get("cookies")
        assert cookies_sent is not None
        assert cookies_sent == {"sid": "abc123", "csrf": "xyz789"}
        assert not any(h.code == "cookies_stale" for h in response.operator_hints)
    finally:
        await sqlite.close()


async def test_chrome_stale_mirror_cookies_flow_with_hint_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale mirror — cookies still flow AND the staleness hint lands exactly once."""
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: _fake_chrome_rows())

    state = make_default_state(_make_settings(source="chrome", stale_h=24))
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(state.settings, sqlite)
    try:
        await jar.refresh()
        # Tamper with last_refresh_at to look 30h old.
        conn = await sqlite.ensure()
        thirty_h_ago = int(time.time()) - 30 * 3600
        await conn.execute(
            "UPDATE cookies_meta SET last_refresh_at = ? WHERE profile = ? AND browser = ?",
            (thirty_h_ago, "Default", "chrome"),
        )
        await conn.commit()

        response = await fetch("https://example.com/", state=state, cookie_jar=lazy(jar))

        cookies_sent = _FakeSession.last_kwargs.get("cookies")
        assert cookies_sent == {"sid": "abc123", "csrf": "xyz789"}
        stale_hints = [h for h in response.operator_hints if h.code == "cookies_stale"]
        assert len(stale_hints) == 1
        assert "30h" in stale_hints[0].message
        assert "24h" in stale_hints[0].message
        assert "a2web cookies refresh" in (stale_hints[0].fix or "")
    finally:
        await sqlite.close()


async def test_never_refreshed_mirror_yields_stale_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No refresh ever — staleness reports `never`."""
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: _fake_chrome_rows())

    state = make_default_state(_make_settings(source="chrome", stale_h=24))
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(state.settings, sqlite)
    try:
        # Note: NO refresh() call — mirror has no row in cookies_meta.
        response = await fetch("https://example.com/", state=state, cookie_jar=lazy(jar))
        stale_hints = [h for h in response.operator_hints if h.code == "cookies_stale"]
        assert len(stale_hints) == 1
        assert "never" in stale_hints[0].message
    finally:
        await sqlite.close()
