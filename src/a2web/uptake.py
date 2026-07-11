"""Suggestion-uptake telemetry — do callers follow a2web's `try_url` drilldowns?

Every `ask` that emits `try_url` targets records them here; every `ask` records
whether its OWN url was a target a prior `ask` suggested. Correlating the two
measures follow-through (openspec `surface-page-links-to-extractor` D12 / task
8.2) — turning "are suggestions useful?" from taste into measurement. The
expectation to test against data: continuation links get followed, speculative
ones don't.

Free functions over the shared a2web sqlite connection (the `cache.py` door),
the same one-file / many-consumers topology as the HTTP cache and cookie mirror.
The schema is idempotent (`CREATE TABLE IF NOT EXISTS`) and applied per-call, so
there is no separate migration step and no module-level applied-schema global
(this module takes the raw connection, never imports `cache`, so it stays free of
that cycle). Writes are best-effort telemetry — the fetcher wraps every call so a
sqlite hiccup can never fail a fetch.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS a2web_url_suggestions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url   TEXT NOT NULL,
    question     TEXT,
    target_url   TEXT NOT NULL,
    off_domain   INTEGER NOT NULL,
    suggested_at INTEGER NOT NULL,
    followed_at  INTEGER
);
"""

# Partial index on the open (un-followed) suggestions — the only rows `note_visit`
# scans. Keeps correlation cheap as the log grows.
_INDEX = "CREATE INDEX IF NOT EXISTS ix_a2web_url_suggestions_open ON a2web_url_suggestions (target_url) WHERE followed_at IS NULL;"


def _normalize(url: str) -> str:
    """Trailing-slash / fragment-insensitive key for target↔visit correlation.

    A suggested href and the URL the caller later fetches often differ only by a
    trailing slash or an anchor fragment; normalize both ends the same way so the
    match lands. Query strings are left intact (they can name a distinct page).
    """
    return url.split("#", 1)[0].rstrip("/")


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    """Idempotent table + index creation (cheap no-op once they exist)."""
    await conn.execute(_SCHEMA)
    await conn.execute(_INDEX)


async def record_suggestions(
    conn: aiosqlite.Connection,
    *,
    source_url: str,
    question: str | None,
    targets: Iterable[tuple[str, bool]],
) -> int:
    """Persist the `try_url` targets one ask emitted.

    `targets` is an iterable of `(target_url, off_domain)`; empty urls are
    dropped. Returns the number of rows stored (0 = nothing to record).
    """
    now = int(time.time())
    rows = [(source_url, question, _normalize(url), int(off_domain), now) for url, off_domain in targets if url]
    if not rows:
        return 0
    await _ensure_schema(conn)
    await conn.executemany(
        "INSERT INTO a2web_url_suggestions (source_url, question, target_url, off_domain, suggested_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    await conn.commit()
    return len(rows)


async def note_visit(conn: aiosqlite.Connection, url: str) -> int:
    """Mark every open suggestion of `url` as followed.

    Returns how many prior suggestions this visit fulfilled — 0 means the caller
    did not arrive here via an a2web suggestion. Called at the top of an ask, so
    it only ever closes suggestions from EARLIER asks (the current ask records its
    own targets afterwards).
    """
    await _ensure_schema(conn)
    cursor = await conn.execute(
        "UPDATE a2web_url_suggestions SET followed_at = ? WHERE target_url = ? AND followed_at IS NULL",
        (int(time.time()), _normalize(url)),
    )
    await conn.commit()
    return cursor.rowcount


__all__ = ("note_visit", "record_suggestions")
