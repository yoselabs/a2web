"""sqlite-backed conditional-GET cache primitives + Resource wrapper.

Schema: one table, profile-scoped, content-hash dedup. Caller controls
the cache write gate (block pages must never reach `cache_put`).
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import time
from pathlib import Path

import aiosqlite

from .paths import cache_dir
from .row import CacheRow

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


async def open_sqlite_with_schema(db_path: Path | None = None) -> aiosqlite.Connection:
    """Open the sqlite database (creating dir + schema as needed).

    `db_path` defaults to `<cache_dir()>/cache.sqlite`.
    """
    target = db_path if db_path is not None else cache_dir() / "cache.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(target)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute(_SCHEMA)
    await conn.execute(_INDEX)
    await conn.commit()
    return conn


async def cache_get(conn: aiosqlite.Connection, url: str, profile_hash: str) -> CacheRow | None:
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


class SqliteResource:
    """Lazy aiosqlite connection + schema bootstrap.

    Opens the underlying sqlite connection on first `_ensure()` call under
    an internal lock. Callers invoke `get` / `put` / `close` directly.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        """Open + schema-bootstrap on first call; cached thereafter."""
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is None:
                self._conn = await open_sqlite_with_schema(self._db_path)
            return self._conn

    async def get(self, url: str, profile_hash: str) -> CacheRow | None:
        """Return a non-expired cache row for (url, profile_hash) or None."""
        conn = await self._ensure()
        return await cache_get(conn, url, profile_hash)

    async def put(
        self,
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
        conn = await self._ensure()
        await cache_put(
            conn,
            url,
            profile_hash,
            etag=etag,
            last_modified=last_modified,
            status_code=status_code,
            content_type=content_type,
            body=body,
            ttl_s=ttl_s,
        )

    async def close(self) -> None:
        """Idempotent close. Re-`_ensure()` after close reopens."""
        if self._conn is None:
            return
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
