"""Tests for the `cookies_refresh` tool + CookiesRouter wiring."""

from __future__ import annotations

import pytest
from a2kit.testing import lazy

from a2web.cookie_jar import CookieJarResource, CookiesRefreshResult, build_cookie_jar
from a2web.packages.cookie_store.models import CookieRow
from a2web.packages.http_cache import SqliteResource
from a2web.routers import CookiesRouter
from a2web.server import app
from a2web.settings import AppSettings
from tests.conftest import make_default_state


def test_cookies_router_registered() -> None:
    """The `refresh` tool is exposed on the app (CLI: `a2web cookies refresh`)."""
    names = {desc.name for desc in app.tools()}
    # a2kit derives MCP tool name from the function name. CLI grouping by
    # router slug ("cookies") gives the user-facing `a2web cookies refresh`.
    assert "refresh" in names


def test_cookies_router_slug() -> None:
    """CLI surface: `a2web cookies refresh`."""
    assert CookiesRouter.slug == "cookies"
    assert any(t.__name__ == "refresh" for t in CookiesRouter.tools)


def test_cookie_jar_provider_registered() -> None:
    """The app exposes a provider for CookieJarResource."""
    assert app.has_provider(CookieJarResource) is True


async def test_refresh_with_source_none_returns_zero_count(tmp_path) -> None:
    """`cookie_source=none` → no DB / Keychain access, returns zero + note."""
    s = AppSettings(cookie_source="none", cookie_profile="Default")
    state = make_default_state(s)
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(s, sqlite)
    try:
        router = CookiesRouter()
        result = await router.refresh(state=state, cookie_jar=lazy(jar))
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

    s = AppSettings(cookie_source="chrome", cookie_profile="Work")
    state = make_default_state(s)
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(s, sqlite)
    try:
        router = CookiesRouter()
        result = await router.refresh(state=state, cookie_jar=lazy(jar))
        assert result.refreshed_count == 42
        assert result.profile == "Work"
        assert result.browser == "chrome"
        assert result.notes == ""

        # Meta was written.
        conn = await sqlite._ensure()
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
    from a2web.packages.cookie_store.models import ChromeCookieAccessError

    def _boom(browser: str, profile: str) -> list[CookieRow]:
        msg = "test: keychain access denied"
        raise ChromeCookieAccessError(msg)

    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", _boom)

    s = AppSettings(cookie_source="chrome", cookie_profile="Default")
    state = make_default_state(s)
    sqlite = SqliteResource(db_path=tmp_path / "cache.sqlite")
    state.sqlite = sqlite
    jar = build_cookie_jar(s, sqlite)
    try:
        router = CookiesRouter()
        result = await router.refresh(state=state, cookie_jar=lazy(jar))
        assert result.refreshed_count == 0
        assert "keychain access denied" in result.notes
    finally:
        await sqlite.close()
