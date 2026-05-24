"""CookieJarResource — domain-coupled mirror of a browser profile's cookies.

Reads cookies from a user's local Chrome (macOS) or Firefox profile via the
pure `packages.cookie_store` package, upserts them into the existing
`SqliteResource` under two tables (`a2web_cookies`, `cookies_meta`), and
serves per-host queries at fetch time without re-touching the source DB.

The resource is opt-in: when `settings.cookie_source == "none"` no work is
done. It's registered via `app.provide(build_cookie_jar)` and surfaced at
the tool seam as `Lazy[CookieJarResource]` so the source DB and Keychain
are only touched when a tool actually awaits the lazy.

Lifecycle follows the project's resource pattern: `__init__` is sync,
`_ensure()` is the lazy lock-guarded bootstrap (creates the two tables),
and `__aenter__` / `__aexit__` are thin wrappers around `_ensure` / `close`.

Mirror semantics:
- `refresh()` is an atomic DELETE + bulk INSERT per (profile, browser) plus
  an `INSERT OR REPLACE INTO cookies_meta`. Tests can reason about it as a
  single transactional swap.
- `get_for_host(host, scheme, path)` filters by domain match, path prefix,
  secure flag, and expiry. Session cookies (`expires_utc IS NULL`) are kept.
- `staleness()` returns the gap between now and `cookies_meta.last_refresh_at`
  and a boolean against `settings.cookie_stale_after_hours`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .packages.cookie_store import read_cookies as _read_cookies
from .packages.cookie_store.models import SameSite
from .packages.cookie_store.store import CookieSource
from .packages.http_cache import SqliteResource
from .settings import AppSettings

if TYPE_CHECKING:
    import aiosqlite


# --------------------------------------------------------------------- #
# Boundary types
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class Cookie:
    """Domain cookie shape — what fetcher phases and tiers receive."""

    name: str
    value: str
    host_key: str
    path: str
    expires_utc: int | None
    is_secure: int
    is_httponly: int
    samesite: SameSite


@dataclass(slots=True)
class StalenessInfo:
    """Result of a staleness probe — agent-readable, no value material."""

    last_refresh_at: datetime | None
    age_hours: float | None
    is_stale: bool


@dataclass(slots=True)
class RefreshResult:
    """Internal refresh outcome (the resource's return value)."""

    profile: str
    browser: CookieSource
    refreshed_count: int
    refreshed_at: datetime


# pydantic API-boundary type for the cookies_refresh tool envelope.
class CookiesRefreshResult(BaseModel):
    """Tool-return envelope for `cookies_refresh`."""

    profile: str
    browser: str
    refreshed_count: int
    refreshed_at: datetime
    notes: str = ""


# --------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------- #


_SCHEMA = """
CREATE TABLE IF NOT EXISTS a2web_cookies (
    profile     TEXT NOT NULL,
    browser     TEXT NOT NULL,
    host_key    TEXT NOT NULL,
    name        TEXT NOT NULL,
    value       TEXT NOT NULL,
    path        TEXT NOT NULL,
    expires_utc INTEGER,
    is_secure   INTEGER NOT NULL,
    is_httponly INTEGER NOT NULL,
    samesite    TEXT,
    PRIMARY KEY (profile, browser, host_key, name, path)
);
"""

_INDEX = "CREATE INDEX IF NOT EXISTS ix_a2web_cookies_host ON a2web_cookies (profile, browser, host_key);"

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS cookies_meta (
    profile         TEXT NOT NULL,
    browser         TEXT NOT NULL,
    last_refresh_at INTEGER NOT NULL,
    refreshed_count INTEGER NOT NULL,
    PRIMARY KEY (profile, browser)
);
"""


# --------------------------------------------------------------------- #
# Domain matching helpers (pure)
# --------------------------------------------------------------------- #


def _host_matches(host_key: str, host: str) -> bool:
    """Chrome-style host match: exact, or `.suffix` matches `host` suffix."""
    if not host:
        return False
    if host_key == host:
        return True
    if host_key.startswith("."):
        suffix = host_key[1:]
        if not suffix:
            return False
        return host == suffix or host.endswith("." + suffix)
    return False


def _path_matches(cookie_path: str, request_path: str) -> bool:
    """RFC 6265 §5.1.4 path match — cookie path is a prefix of request path."""
    if not cookie_path or cookie_path == "/":
        return True
    if request_path == cookie_path:
        return True
    if request_path.startswith(cookie_path):
        # Boundary: cookie_path either ends with "/" or the request path's
        # next character is "/".
        return cookie_path.endswith("/") or request_path[len(cookie_path)] == "/"
    return False


# --------------------------------------------------------------------- #
# Resource
# --------------------------------------------------------------------- #


class CookieJarResource:
    """Opt-in cookie mirror. Pairs with `SqliteResource` for storage."""

    def __init__(self, settings: AppSettings, sqlite: SqliteResource) -> None:
        self._settings = settings
        self._sqlite = sqlite
        self._lock = asyncio.Lock()
        self._tables_ready = False

    # ----- internal bootstrap -----

    async def _ensure(self) -> aiosqlite.Connection:
        """Open the underlying sqlite (via SqliteResource) and create tables."""
        conn = await self._sqlite._ensure()
        if self._tables_ready:
            return conn
        async with self._lock:
            if self._tables_ready:
                return conn
            await conn.execute(_SCHEMA)
            await conn.execute(_INDEX)
            await conn.execute(_META_SCHEMA)
            await conn.commit()
            self._tables_ready = True
        return conn

    async def close(self) -> None:
        """No-op — the SqliteResource owns the connection."""
        return None

    # ----- refresh -----

    async def refresh(self) -> RefreshResult:
        """Read the configured browser profile and atomically swap the mirror."""
        s = self._settings
        if s.cookie_source == "none":
            return RefreshResult(
                profile=s.cookie_profile,
                browser="chrome",  # nominal — caller branches on count == 0
                refreshed_count=0,
                refreshed_at=datetime.now(UTC),
            )
        browser: CookieSource = s.cookie_source  # type: ignore[assignment]
        profile = s.cookie_profile

        # Read in a thread — browser-cookie3 does subprocess + sqlite I/O.
        rows = await asyncio.to_thread(_read_cookies, browser, profile)

        conn = await self._ensure()
        refreshed_at_unix = int(time.time())
        async with self._lock:
            await conn.execute("BEGIN")
            try:
                await conn.execute(
                    "DELETE FROM a2web_cookies WHERE profile = ? AND browser = ?",
                    (profile, browser),
                )
                if rows:
                    await conn.executemany(
                        "INSERT INTO a2web_cookies "
                        "(profile, browser, host_key, name, value, path, "
                        "expires_utc, is_secure, is_httponly, samesite) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                profile,
                                browser,
                                r.host_key,
                                r.name,
                                r.value,
                                r.path,
                                r.expires_utc,
                                r.is_secure,
                                r.is_httponly,
                                r.samesite,
                            )
                            for r in rows
                        ],
                    )
                await conn.execute(
                    "INSERT OR REPLACE INTO cookies_meta (profile, browser, last_refresh_at, refreshed_count) VALUES (?, ?, ?, ?)",
                    (profile, browser, refreshed_at_unix, len(rows)),
                )
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise

        return RefreshResult(
            profile=profile,
            browser=browser,
            refreshed_count=len(rows),
            refreshed_at=datetime.fromtimestamp(refreshed_at_unix, tz=UTC),
        )

    # ----- queries -----

    async def get_for_host(self, host: str, scheme: str, path: str) -> list[Cookie]:
        """Return cookies applicable to (host, scheme, path), filtered."""
        s = self._settings
        if s.cookie_source == "none":
            return []
        browser = s.cookie_source
        profile = s.cookie_profile
        conn = await self._ensure()

        now = int(time.time())
        is_https = scheme.lower() == "https"

        async with conn.execute(
            "SELECT host_key, name, value, path, expires_utc, "
            "is_secure, is_httponly, samesite "
            "FROM a2web_cookies WHERE profile = ? AND browser = ?",
            (profile, browser),
        ) as cursor:
            rows = await cursor.fetchall()

        out: list[Cookie] = []
        for r in rows:
            host_key, name, value, cpath, expires_utc, is_secure, is_httponly, samesite = r
            if not _host_matches(host_key, host):
                continue
            if not _path_matches(cpath, path):
                continue
            if is_secure and not is_https:
                continue
            if expires_utc is not None and expires_utc <= now:
                continue
            out.append(
                Cookie(
                    name=name,
                    value=value,
                    host_key=host_key,
                    path=cpath,
                    expires_utc=expires_utc,
                    is_secure=is_secure,
                    is_httponly=is_httponly,
                    samesite=samesite,
                ),
            )
        return out

    async def staleness(self) -> StalenessInfo:
        """Report mirror freshness against `cookie_stale_after_hours`."""
        s = self._settings
        threshold_h = s.cookie_stale_after_hours
        if s.cookie_source == "none":
            # Inert — caller should not invoke this; return non-stale to be safe.
            return StalenessInfo(last_refresh_at=None, age_hours=None, is_stale=False)
        browser = s.cookie_source
        profile = s.cookie_profile

        conn = await self._ensure()
        async with conn.execute(
            "SELECT last_refresh_at FROM cookies_meta WHERE profile = ? AND browser = ?",
            (profile, browser),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None or row[0] is None:
            return StalenessInfo(last_refresh_at=None, age_hours=None, is_stale=True)
        last_unix = int(row[0])
        last = datetime.fromtimestamp(last_unix, tz=UTC)
        age_h = (time.time() - last_unix) / 3600.0
        is_stale = age_h > threshold_h
        return StalenessInfo(last_refresh_at=last, age_hours=age_h, is_stale=is_stale)

    # ----- framework-facing CM -----

    async def __aenter__(self) -> CookieJarResource:
        await self._ensure()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


def build_cookie_jar(settings: AppSettings, sqlite: SqliteResource) -> CookieJarResource:
    """Named factory — a2kit v0.36+ requires return annotation, no lambdas."""
    return CookieJarResource(settings, sqlite)


def redact_cookie_for_event(cookie: Cookie) -> dict[str, str | int]:
    """Project a Cookie to a redacted dict suitable for LDD / structlog payloads.

    Carries name + host_key + path + value LENGTH (not value). Values are the
    entire secret being mirrored; emitting them to any observability sink
    would defeat the redaction discipline.
    """
    return {
        "name": cookie.name,
        "host_key": cookie.host_key,
        "path": cookie.path,
        "value_length": len(cookie.value),
    }


__all__ = (
    "Cookie",
    "CookieJarResource",
    "CookiesRefreshResult",
    "RefreshResult",
    "StalenessInfo",
    "build_cookie_jar",
    "redact_cookie_for_event",
)
