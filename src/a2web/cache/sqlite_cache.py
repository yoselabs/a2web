"""sqlite-backed conditional-GET cache. Block pages NEVER enter this cache.

Schema is one table, profile-scoped, content-hash dedup. The cache write
gate lives in `fetcher.py` — only `Verdict.ok` results land here.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from ..settings import AppSettings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    url            TEXT NOT NULL,
    profile_hash   TEXT NOT NULL,
    etag           TEXT,
    last_modified  TEXT,
    fetched_at     INTEGER NOT NULL,
    expires_at     INTEGER NOT NULL,
    status_code    INTEGER NOT NULL,
    content_type   TEXT,
    content_hash   TEXT NOT NULL,
    body           BLOB NOT NULL,
    PRIMARY KEY (url, profile_hash)
);
"""

_INDEX = "CREATE INDEX IF NOT EXISTS cache_content_hash ON cache(content_hash);"


@dataclass(slots=True)
class CacheRow:
    url: str
    profile_hash: str
    etag: str | None
    last_modified: str | None
    fetched_at: int
    expires_at: int
    status_code: int
    content_type: str | None
    content_hash: str
    body: bytes


def cache_dir() -> Path:
    """Resolve the cache directory, honoring `$A2WEB_CACHE_DIR`."""
    override = os.environ.get("A2WEB_CACHE_DIR")
    return Path(override).expanduser() if override else Path.home() / ".a2web"


async def open_sqlite_with_schema(_settings: AppSettings) -> aiosqlite.Connection:
    """Open the sqlite database (creating dir + schema as needed)."""
    cache_root = cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(cache_root / "cache.sqlite")
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute(_SCHEMA)
    await conn.execute(_INDEX)
    await conn.commit()
    return conn


def compute_profile_hash(settings: AppSettings) -> str:
    """Hash settings fields that affect upstream request shape.

    PR3: `default_ua` + `stealth`. PR7 will fold proxy id in.
    """
    payload = f"{settings.default_ua}|{settings.stealth}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


async def cache_get(
    conn: aiosqlite.Connection, url: str, profile_hash: str
) -> CacheRow | None:
    """Return a non-expired row for (url, profile_hash) or None."""
    async with conn.execute(
        "SELECT url, profile_hash, etag, last_modified, fetched_at, expires_at, "
        "status_code, content_type, content_hash, body FROM cache "
        "WHERE url = ? AND profile_hash = ? AND expires_at > ?",
        (url, profile_hash, int(time.time())),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return CacheRow(
        url=row[0],
        profile_hash=row[1],
        etag=row[2],
        last_modified=row[3],
        fetched_at=row[4],
        expires_at=row[5],
        status_code=row[6],
        content_type=row[7],
        content_hash=row[8],
        body=gzip.decompress(row[9]),
    )


async def cache_put(
    conn: aiosqlite.Connection,
    url: str,
    profile_hash: str,
    *,
    etag: str | None,
    last_modified: str | None,
    status_code: int,
    content_type: str | None,
    body: bytes,
    ttl_s: int,
) -> None:
    """Insert or replace one cache row. Caller MUST gate-check first."""
    now = int(time.time())
    content_hash = hashlib.sha256(body).hexdigest()
    compressed = gzip.compress(body)
    await conn.execute(
        "INSERT OR REPLACE INTO cache "
        "(url, profile_hash, etag, last_modified, fetched_at, expires_at, "
        "status_code, content_type, content_hash, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            url,
            profile_hash,
            etag,
            last_modified,
            now,
            now + ttl_s,
            status_code,
            content_type,
            content_hash,
            compressed,
        ),
    )
    await conn.commit()


def is_live_only(url: str, settings: AppSettings) -> bool:
    """Return True if `url`'s host should bypass the cache entirely."""
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith(f".{h}") for h in settings.live_only_hosts)
