"""a2web cache seam — composes the shelf `sqlite-resource` + `http-cache` primitives.

Domain policy lives here; the generic mechanics live on the shelf. This module
pins a2web's `$A2WEB_CACHE_DIR` default-path resolution, applies the cache schema
on open, and adds the `(url, profile_hash)` get/put accessor the fetcher expects —
composing `sqlite_resource.SqliteResource` (connection lifecycle) and `http_cache`'s
free functions (conditional-GET cache mechanics).

a2web keeps its HTTP cache, its extraction-answer cache, and its cookie mirror in
ONE sqlite file behind a single shared connection: the fetcher uses `.get`/`.put`
here; `ExtractionCache` and the cookie jar share the same connection via `ensure()`.
The composite `http_cache.HttpCache` owns a private connection, so it does not fit
that one-file/three-consumer topology — a2web uses the free-function door instead.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
from http_cache import CacheRow, apply_schema, cache_get, cache_put
from sqlite_resource import SqliteResource as _SqliteResource


def cache_dir() -> Path:
    """Resolve the cache directory, honoring `$A2WEB_CACHE_DIR`."""
    override = os.environ.get("A2WEB_CACHE_DIR")
    return Path(override).expanduser() if override else Path.home() / ".a2web"


async def _migrate_and_apply_schema(conn: aiosqlite.Connection) -> None:
    """Apply the cache schema, dropping a legacy-shaped `cache` table first.

    Before the cache primitive was promoted to the shelf, a2web keyed the cache on
    a `profile_hash` column; `http_cache` renamed it to the generic `variant`. A
    `CREATE TABLE IF NOT EXISTS` would leave a pre-existing legacy table in place,
    and every `variant` query against it would raise `no such column: variant`. The
    cache is regenerable, so drop a legacy-shaped table and let `apply_schema`
    recreate it fresh — existing installs rebuild rather than crash.
    """
    async with conn.execute("PRAGMA table_info(cache)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if columns and "variant" not in columns:
        await conn.execute("DROP TABLE cache")
    await apply_schema(conn)


class SqliteResource(_SqliteResource):
    """a2web's shared sqlite connection: default cache-dir path + cache schema.

    Composes the shelf `SqliteResource`, pinning a2web's domain policy — the default
    `<cache_dir()>/cache.sqlite` path and the on-open cache schema — and adds the
    `(url, profile_hash)` get/put accessor the fetcher uses. The extraction cache and
    cookie jar share the same open connection via `ensure()` / `conn`.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        target = db_path if db_path is not None else cache_dir() / "cache.sqlite"
        super().__init__(target, on_open=_migrate_and_apply_schema)

    async def get(self, url: str, profile_hash: str) -> CacheRow | None:
        """Return a non-expired cached row for `(url, profile_hash)`, or None."""
        return await cache_get(await self.ensure(), url, profile_hash)

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
        await cache_put(
            await self.ensure(),
            url,
            profile_hash,
            etag=etag,
            last_modified=last_modified,
            status_code=status_code,
            content_type=content_type,
            body=body,
            ttl_s=ttl_s,
        )


async def open_sqlite_with_schema(db_path: Path | None = None) -> aiosqlite.Connection:
    """Open a connection with the cache schema applied (compat shim over `SqliteResource`)."""
    return await SqliteResource(db_path).ensure()


__all__ = (
    "CacheRow",
    "SqliteResource",
    "cache_dir",
    "cache_get",
    "cache_put",
    "open_sqlite_with_schema",
)
