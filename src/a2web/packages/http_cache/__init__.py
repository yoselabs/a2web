"""sqlite-backed conditional-GET cache — in-tree microsofware.

Pure cache primitives: schema bootstrap, content-hash dedup, conditional
GET, gzip-compressed body. Zero a2web-domain imports.

Boundary types (`CacheRow`, `SqliteResource`) are package-owned. Domain
policy (profile-hash composition, live-only host bypass) lives at the
a2web seam in `a2web.cache.sqlite_cache`.
"""

from __future__ import annotations

from .paths import cache_dir
from .row import CacheRow
from .sqlite import SqliteResource, cache_get, cache_put, open_sqlite_with_schema

__all__ = (
    "CacheRow",
    "SqliteResource",
    "cache_dir",
    "cache_get",
    "cache_put",
    "open_sqlite_with_schema",
)
