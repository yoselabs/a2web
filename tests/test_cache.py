"""Sqlite cache tests — schema, profile_hash isolation, live-only bypass."""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.cache.sqlite_cache import (
    cache_get,
    cache_put,
    compute_profile_hash,
    is_live_only,
    open_sqlite_with_schema,
)
from a2web.settings import AppSettings


@pytest.fixture(autouse=True)
def _isolate_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A2WEB_CACHE_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_schema_creation() -> None:
    conn = await open_sqlite_with_schema(AppSettings())
    try:
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cache'") as cur:
            row = await cur.fetchone()
        assert row is not None and row[0] == "cache"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_put_get_roundtrip() -> None:
    conn = await open_sqlite_with_schema(AppSettings())
    try:
        ph = compute_profile_hash(AppSettings())
        await cache_put(
            conn,
            "https://x/y",
            ph,
            etag='W/"abc"',
            last_modified="Wed, 01 Apr 2026 09:00:00 GMT",
            status_code=200,
            content_type="text/html",
            body=b"<html>hi</html>",
            ttl_s=3600,
        )
        row = await cache_get(conn, "https://x/y", ph)
        assert row is not None
        assert row.body == b"<html>hi</html>"
        assert row.etag == 'W/"abc"'
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_profile_hash_isolation() -> None:
    conn = await open_sqlite_with_schema(AppSettings())
    try:
        ph_a = compute_profile_hash(AppSettings(default_ua="UA-A"))
        ph_b = compute_profile_hash(AppSettings(default_ua="UA-B"))
        assert ph_a != ph_b

        await cache_put(
            conn,
            "https://x/y",
            ph_a,
            etag=None,
            last_modified=None,
            status_code=200,
            content_type="text/html",
            body=b"A",
            ttl_s=3600,
        )
        row_a = await cache_get(conn, "https://x/y", ph_a)
        row_b = await cache_get(conn, "https://x/y", ph_b)
        assert row_a is not None
        assert row_b is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_expired_row_returns_none() -> None:
    conn = await open_sqlite_with_schema(AppSettings())
    try:
        ph = compute_profile_hash(AppSettings())
        await cache_put(
            conn,
            "https://x/y",
            ph,
            etag=None,
            last_modified=None,
            status_code=200,
            content_type="text/html",
            body=b"data",
            ttl_s=-1,  # already expired
        )
        row = await cache_get(conn, "https://x/y", ph)
        assert row is None
    finally:
        await conn.close()


def test_live_only_bypass() -> None:
    settings = AppSettings(live_only_hosts=["reddit.com"])
    assert is_live_only("https://reddit.com/r/x", settings) is True
    assert is_live_only("https://www.reddit.com/r/x", settings) is True
    assert is_live_only("https://example.com/x", settings) is False
