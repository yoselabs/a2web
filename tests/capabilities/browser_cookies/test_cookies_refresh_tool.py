"""Tests for the `refresh` cookies tool.

Post-sunset the tool is a closure registered on the FastMCP server, not a
method on a `CookiesRouter` class, so these drive it through a real client
instead of calling the bound method. That is the more honest test anyway: the
old form asserted on a Python call the agent never makes, and could not have
caught the tool failing to register at all.
"""

from __future__ import annotations

import pytest
from async_scope import lazy
from browser_cookies.models import CookieRow

from a2web.cache import SqliteResource
from a2web.components import build_components
from a2web.cookie_jar import CookiesRefreshResult, build_cookie_jar
from a2web.settings import AppSettings
from tests._helpers.mcp import mcp_client


async def _refresh(settings: AppSettings, jar: object) -> CookiesRefreshResult:
    """Drive the real `refresh` tool with a pre-built cookie jar."""
    import dataclasses

    parts = dataclasses.replace(build_components(settings=settings), cookie_jar=lazy(jar))
    async with mcp_client(settings=settings, components=parts) as client:
        result = await client.call_tool("cookies_refresh", {})
    return CookiesRefreshResult.model_validate(result.structured_content)


async def test_refresh_with_source_none_returns_zero_count(tmp_path) -> None:
    """`cookie_source=none` → no DB / Keychain access, returns zero + note."""
    s = AppSettings(expose_cookies_tool=True, cookie_source="none", cookie_profile="Default")
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    jar = build_cookie_jar(s, sqlite)
    try:
        result = await _refresh(s, jar)
        assert isinstance(result, CookiesRefreshResult)
        assert result.refreshed_count == 0
        assert "none" in result.notes.lower() or "disabled" in result.notes.lower()
    finally:
        await sqlite.close()


async def test_refresh_with_chrome_source_returns_count(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cookie_source=chrome` with fake reader → count + meta updated."""
    rows = [
        CookieRow(
            host_key=".example.com",
            name=f"c{i}",
            value=f"v{i}",
            path="/",
            expires_utc=None,
            is_secure=1,
            is_httponly=1,
            samesite="lax",
        )
        for i in range(42)
    ]
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: rows)

    s = AppSettings(expose_cookies_tool=True, cookie_source="chrome", cookie_profile="Work")
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    jar = build_cookie_jar(s, sqlite)
    try:
        result = await _refresh(s, jar)
        assert result.refreshed_count == 42
        assert result.profile == "Work"
        assert result.browser == "chrome"
        assert result.notes == ""

        # Meta was written.
        conn = await sqlite.ensure()
        async with conn.execute(
            "SELECT refreshed_count FROM cookies_meta WHERE profile=? AND browser=?",
            ("Work", "chrome"),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None and row[0] == 42
    finally:
        await sqlite.close()


async def test_refresh_handles_chrome_access_error_gracefully(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reader raising ChromeCookieAccessError → zero count + descriptive note."""
    from browser_cookies.models import ChromeCookieAccessError

    def _boom(browser: str, profile: str) -> list[CookieRow]:
        msg = "test: keychain access denied"
        raise ChromeCookieAccessError(msg)

    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", _boom)

    s = AppSettings(expose_cookies_tool=True, cookie_source="chrome", cookie_profile="Default")
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    jar = build_cookie_jar(s, sqlite)
    try:
        result = await _refresh(s, jar)
        assert result.refreshed_count == 0
        assert "keychain access denied" in result.notes
    finally:
        await sqlite.close()
