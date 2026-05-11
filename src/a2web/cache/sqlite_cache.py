"""a2web seam over `packages.http_cache`.

The cache primitives (`CacheRow`, `cache_get`/`cache_put`, `SqliteResource`,
`cache_dir`, `open_sqlite_with_schema`) live in
`a2web.packages.http_cache` as in-tree microsofware. This module is the
a2web seam: it re-exports the primitives and adds the domain-coupled
bits (profile-hash composition over `AppSettings`, live-only host
bypass) that the orchestrator needs.

Block pages NEVER enter this cache — the write gate lives in `fetcher.py`.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..packages.http_cache import (
    CacheRow,
    cache_dir,
    cache_get,
    cache_put,
)
from ..packages.http_cache import (
    SqliteResource as _PackageSqliteResource,
)
from ..packages.http_cache import (
    open_sqlite_with_schema as _package_open,
)
from ..settings import AppSettings

if TYPE_CHECKING:
    import aiosqlite

__all__ = (
    "CacheRow",
    "SqliteResource",
    "cache_dir",
    "cache_get",
    "cache_get_dir",
    "cache_put",
    "compute_profile_hash",
    "is_live_only",
    "open_sqlite_with_schema",
)


async def open_sqlite_with_schema(_settings: AppSettings | None = None) -> aiosqlite.Connection:
    """a2web seam over `packages.http_cache.open_sqlite_with_schema`.

    Accepts (and ignores) `AppSettings` for backward compat — the
    package layer takes a `Path | None` and resolves via `$A2WEB_CACHE_DIR`
    / `cache_dir()`.
    """
    return await _package_open(None)


class SqliteResource(_PackageSqliteResource):
    """a2web seam: accepts `AppSettings` and constructs the package's
    `SqliteResource` against the resolved cache path.

    The settings object is currently unused at the package layer (cache
    location comes from `cache_dir()` / `$A2WEB_CACHE_DIR`). It is held
    on the seam in case future fields (e.g. operator-specified DB path)
    need to influence construction.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        super().__init__(db_path=None)


def compute_profile_hash(settings: AppSettings) -> str:
    """Hash settings fields that affect upstream request shape.

    PR3: `default_ua` + `stealth`. PR7 will fold proxy id in.
    """
    payload = f"{settings.default_ua}|{settings.stealth}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def is_live_only(url: str, settings: AppSettings) -> bool:
    """Return True if `url`'s host should bypass the cache entirely."""
    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith(f".{h}") for h in settings.live_only_hosts)


# Backward-compat re-export alias kept off __all__ to avoid encouraging new use.
cache_get_dir = cache_dir
