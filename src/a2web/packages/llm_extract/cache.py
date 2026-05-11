"""Extraction-answer cache — sqlite-backed LRU over (content, ask, model).

Mirrors Claude Code WebFetch's 15-minute self-cleaning cache (research/123:
`sg5 = 900000 ms`). Key is sha256(content_md) + sha256(ask) + model_id, so
the same (content, question, model) tuple returns the same answer until
TTL elapses. Different model = separate cache entry — model swaps never
read stale answers.

Lives in the SAME sqlite file as the HTTP cache (`AppState.sqlite`)
under a different table. The schema is created lazily on first use so the
core a2web install (no `[llm]` extra) is unaffected.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS extraction_cache (
    content_hash    TEXT NOT NULL,
    ask_hash        TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    template_name   TEXT NOT NULL,
    answer          TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    cached_at       INTEGER NOT NULL,
    expires_at      INTEGER NOT NULL,
    PRIMARY KEY (content_hash, ask_hash, model_id, template_name)
);
"""
_INDEX = "CREATE INDEX IF NOT EXISTS extraction_cache_expires ON extraction_cache(expires_at);"


def hash_text(text: str) -> str:
    """Stable sha256 of UTF-8 bytes. Used for the cache key components."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class ExtractionCacheRow:
    content_hash: str
    ask_hash: str
    model_id: str
    template_name: str
    answer: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    cached_at: int
    expires_at: int


class ExtractionCache:
    """Async sqlite-backed cache. Construction is cheap (no I/O until used).

    Usage:
        cache = ExtractionCache(sqlite_conn, ttl_s=900)
        await cache.ensure_schema()
        hit = await cache.get(content_hash, ask_hash, model_id, template_name)
        if hit is None:
            ... call provider ...
            await cache.put(row)
    """

    def __init__(
        self,
        sqlite_conn: aiosqlite.Connection,
        *,
        ttl_s: int = 900,
    ) -> None:
        self._conn = sqlite_conn
        self._ttl_s = max(0, int(ttl_s))
        self._schema_ready = False

    @property
    def ttl_s(self) -> int:
        return self._ttl_s

    async def ensure_schema(self) -> None:
        """Create the table + index if missing. Idempotent."""
        if self._schema_ready:
            return
        await self._conn.executescript(_SCHEMA + _INDEX)
        await self._conn.commit()
        self._schema_ready = True

    async def get(
        self,
        *,
        content_hash: str,
        ask_hash: str,
        model_id: str,
        template_name: str,
    ) -> ExtractionCacheRow | None:
        """Return a cached row if present and unexpired, else None.

        Expired rows are deleted lazily on the read that surfaces them.
        """
        await self.ensure_schema()
        now = _now()
        cursor = await self._conn.execute(
            "SELECT content_hash, ask_hash, model_id, template_name, answer, "
            "prompt_tokens, completion_tokens, cost_usd, latency_ms, "
            "cached_at, expires_at "
            "FROM extraction_cache WHERE content_hash=? AND ask_hash=? "
            "AND model_id=? AND template_name=? LIMIT 1",
            (content_hash, ask_hash, model_id, template_name),
        )
        record = await cursor.fetchone()
        await cursor.close()
        if record is None:
            return None
        row = ExtractionCacheRow(
            content_hash=str(record[0]),
            ask_hash=str(record[1]),
            model_id=str(record[2]),
            template_name=str(record[3]),
            answer=str(record[4]),
            prompt_tokens=int(record[5]),
            completion_tokens=int(record[6]),
            cost_usd=float(record[7]),
            latency_ms=int(record[8]),
            cached_at=int(record[9]),
            expires_at=int(record[10]),
        )
        if row.expires_at <= now:
            # Lazy eviction — also drops any other expired rows along the way.
            await self._evict_expired(now)
            return None
        return row

    async def put(
        self,
        *,
        content_hash: str,
        ask_hash: str,
        model_id: str,
        template_name: str,
        answer: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        """Insert or replace a cache entry. expires_at = cached_at + ttl_s."""
        await self.ensure_schema()
        now = _now()
        expires = now + self._ttl_s
        await self._conn.execute(
            "INSERT OR REPLACE INTO extraction_cache "
            "(content_hash, ask_hash, model_id, template_name, answer, "
            "prompt_tokens, completion_tokens, cost_usd, latency_ms, "
            "cached_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                content_hash,
                ask_hash,
                model_id,
                template_name,
                answer,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                latency_ms,
                now,
                expires,
            ),
        )
        await self._conn.commit()

    async def evict_expired(self) -> int:
        """Manually evict expired rows. Returns rows-removed count."""
        return await self._evict_expired(_now())

    async def _evict_expired(self, now: int) -> int:
        cursor = await self._conn.execute("DELETE FROM extraction_cache WHERE expires_at <= ?", (now,))
        await self._conn.commit()
        return cursor.rowcount or 0

    async def size(self) -> int:
        """Return the row count (post-eviction)."""
        await self.ensure_schema()
        cursor = await self._conn.execute("SELECT COUNT(*) FROM extraction_cache")
        record = await cursor.fetchone()
        await cursor.close()
        return int(record[0]) if record else 0


def _now() -> int:
    return int(time.time())


def make_key(*, content: str, ask: str) -> dict[str, Any]:
    """Helper for callers: hash content + ask in one call. Returns
    {content_hash, ask_hash} (model_id + template_name added by caller)."""
    return {"content_hash": hash_text(content), "ask_hash": hash_text(ask)}


__all__ = [
    "ExtractionCache",
    "ExtractionCacheRow",
    "hash_text",
    "make_key",
]
