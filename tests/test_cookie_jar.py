"""CookieJarResource tests — mirror semantics, domain matching, staleness."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from a2web.cookie_jar import CookieJarResource, build_cookie_jar
from a2web.packages.cookie_store import models as cs_models
from a2web.packages.cookie_store.models import CookieRow
from a2web.packages.http_cache import SqliteResource
from a2web.settings import AppSettings


def _settings(*, source: str = "chrome", profile: str = "Default", stale_h: int = 24) -> AppSettings:
    return AppSettings(
        cookie_source=source,
        cookie_profile=profile,
        cookie_stale_after_hours=stale_h,
    )


@pytest.fixture
async def sqlite_res(tmp_path: Path):
    res = SqliteResource(db_path=tmp_path / "cache.sqlite")
    try:
        yield res
    finally:
        await res.close()


def _row(
    host: str = ".example.com",
    name: str = "sid",
    value: str = "abc",
    path: str = "/",
    expires: int | None = None,
    secure: int = 0,
    httponly: int = 0,
    samesite: cs_models.SameSite = None,
) -> CookieRow:
    return CookieRow(
        host_key=host,
        name=name,
        value=value,
        path=path,
        expires_utc=expires,
        is_secure=secure,
        is_httponly=httponly,
        samesite=samesite,
    )


# ----------- lifecycle + factory -----------


async def test_factory_returns_resource(sqlite_res: SqliteResource) -> None:
    jar = build_cookie_jar(_settings(), sqlite_res)
    assert isinstance(jar, CookieJarResource)


async def test_aenter_creates_tables(sqlite_res: SqliteResource) -> None:
    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        conn = await sqlite_res._ensure()
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('a2web_cookies', 'cookies_meta')",
        ) as cursor:
            tables = {row[0] for row in await cursor.fetchall()}
    assert tables == {"a2web_cookies", "cookies_meta"}


# ----------- refresh -----------


async def test_refresh_atomic_swap(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refresh replaces existing rows for the same (profile, browser)."""
    rows_v1 = [_row(name=f"c{i}") for i in range(5)]
    rows_v2 = [_row(name=f"d{i}") for i in range(3)]

    import a2web.cookie_jar as cj

    calls = {"n": 0}

    def fake_read(browser: str, profile: str) -> list[CookieRow]:
        calls["n"] += 1
        return rows_v1 if calls["n"] == 1 else rows_v2

    monkeypatch.setattr(cj, "_read_cookies", fake_read)

    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        r1 = await jar.refresh()
        assert r1.refreshed_count == 5
        r2 = await jar.refresh()
        assert r2.refreshed_count == 3
        conn = await sqlite_res._ensure()
        async with conn.execute(
            "SELECT name FROM a2web_cookies WHERE profile='Default' AND browser='chrome'",
        ) as cursor:
            names = sorted(row[0] for row in await cursor.fetchall())
    assert names == ["d0", "d1", "d2"]


async def test_refresh_isolates_profile_browser(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refreshing one (profile, browser) doesn't disturb other pairs."""
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: [_row(name=f"{p}-{b}")])

    s1 = AppSettings(cookie_source="chrome", cookie_profile="A")
    s2 = AppSettings(cookie_source="firefox", cookie_profile="A")
    jar_a = build_cookie_jar(s1, sqlite_res)
    jar_b = build_cookie_jar(s2, sqlite_res)

    async with jar_a, jar_b:
        await jar_a.refresh()
        await jar_b.refresh()
        conn = await sqlite_res._ensure()
        async with conn.execute(
            "SELECT profile, browser, name FROM a2web_cookies ORDER BY browser",
        ) as cursor:
            rows = await cursor.fetchall()
    assert rows == [("A", "chrome", "A-chrome"), ("A", "firefox", "A-firefox")]


# ----------- get_for_host -----------


async def test_host_match_exact_and_subdomain(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    rows = [
        _row(host=".example.com", name="dom"),
        _row(host="example.com", name="hostonly"),
        _row(host="other.com", name="nope"),
    ]
    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: rows)

    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        await jar.refresh()
        sub = await jar.get_for_host("api.example.com", "https", "/")
        exact = await jar.get_for_host("example.com", "https", "/")
    names_sub = {c.name for c in sub}
    names_exact = {c.name for c in exact}
    assert names_sub == {"dom"}
    assert names_exact == {"dom", "hostonly"}


async def test_secure_flag_drops_on_http(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: [_row(name="s", secure=1), _row(name="i", secure=0)])

    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        await jar.refresh()
        http_cookies = await jar.get_for_host("example.com", "http", "/")
        https_cookies = await jar.get_for_host("example.com", "https", "/")
    assert {c.name for c in http_cookies} == {"i"}
    assert {c.name for c in https_cookies} == {"s", "i"}


async def test_path_prefix(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    monkeypatch.setattr(
        cj,
        "_read_cookies",
        lambda b, p: [
            _row(name="root", path="/"),
            _row(name="admin", path="/admin"),
            _row(name="adminish", path="/admin"),
        ],
    )
    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        await jar.refresh()
        public = await jar.get_for_host("example.com", "https", "/public/x")
        admin = await jar.get_for_host("example.com", "https", "/admin/users")
    assert {c.name for c in public} == {"root"}
    assert {c.name for c in admin} == {"root", "admin", "adminish"}


async def test_expired_cookies_dropped(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    past = int(time.time()) - 3600
    future = int(time.time()) + 3600
    monkeypatch.setattr(
        cj,
        "_read_cookies",
        lambda b, p: [
            _row(name="dead", expires=past),
            _row(name="live", expires=future),
            _row(name="session", expires=None),
        ],
    )
    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        await jar.refresh()
        got = await jar.get_for_host("example.com", "https", "/")
    assert {c.name for c in got} == {"live", "session"}


# ----------- staleness -----------


async def test_staleness_never_refreshed(sqlite_res: SqliteResource) -> None:
    jar = build_cookie_jar(_settings(), sqlite_res)
    async with jar:
        info = await jar.staleness()
    assert info.last_refresh_at is None
    assert info.age_hours is None
    assert info.is_stale is True


async def test_staleness_fresh(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: [])
    jar = build_cookie_jar(_settings(stale_h=24), sqlite_res)
    async with jar:
        await jar.refresh()
        info = await jar.staleness()
    assert info.is_stale is False
    assert info.age_hours is not None and info.age_hours < 1


async def test_staleness_stale(sqlite_res: SqliteResource, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2web.cookie_jar as cj

    monkeypatch.setattr(cj, "_read_cookies", lambda b, p: [])
    jar = build_cookie_jar(_settings(stale_h=24), sqlite_res)
    async with jar:
        await jar.refresh()
        conn = await sqlite_res._ensure()
        thirty_h_ago = int(time.time()) - 30 * 3600
        await conn.execute(
            "UPDATE cookies_meta SET last_refresh_at = ? WHERE profile = ? AND browser = ?",
            (thirty_h_ago, "Default", "chrome"),
        )
        await conn.commit()
        info = await jar.staleness()
    assert info.is_stale is True
    assert info.age_hours is not None and 29 < info.age_hours < 31


async def test_inert_when_source_none(sqlite_res: SqliteResource) -> None:
    jar = build_cookie_jar(_settings(source="none"), sqlite_res)
    async with jar:
        info = await jar.staleness()
        got = await jar.get_for_host("example.com", "https", "/")
    assert info.is_stale is False
    assert got == []
