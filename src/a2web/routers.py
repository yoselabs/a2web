"""a2web routers — `WebRouter` (fetch) + `LogsRouter` (replay/tail/grep).

Routers are grouped by surface area: web-fetch and log-introspection are
distinct concerns and live in distinct routers so the CLI surface
matches (`a2web web fetch`, `a2web logs replay`).
"""

from __future__ import annotations

import asyncio
from typing import Any

import a2kit
import anyio
from pydantic import BaseModel, Field

from .events import EventBus, mcp_progress_sink, otel_sink
from .fetcher import fetch as orchestrate
from .log.reader import find_last_for_url, grep_records, tail_records
from .log.record import LogRecord
from .models import FetchResponse
from .state import AppState
from .utils.duration import parse_duration


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    @a2kit.read()
    async def fetch(self, *, url: str, state: AppState, ctx: a2kit.ToolContext) -> FetchResponse:
        """Fetch content from a URL."""
        bus = EventBus()
        mcp_recv = bus.subscribe()
        otel_recv = bus.subscribe()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mcp_progress_sink, ctx, mcp_recv)
            tg.start_soon(otel_sink, otel_recv)
            try:
                response = await orchestrate(url, state=state, bus=bus)
            finally:
                await bus.aclose()
        return response


# ---- LogsRouter ---- (PR10) -------------------------------------------------


class LogRecordModel(BaseModel):
    """Pydantic projection of `log.record.LogRecord` for tool returns."""

    ts: str
    url: str
    final_url: str
    host: str
    tier: str
    status: str
    verdict: str
    cache: str
    total_ms: int
    content_chars: int
    title: str | None = None
    error: str | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class LogReplayResponse(BaseModel):
    found: bool
    record: LogRecordModel | None = None
    narrative: str = ""


class LogTailResponse(BaseModel):
    count: int
    records: list[LogRecordModel] = Field(default_factory=list)


class LogGrepResponse(BaseModel):
    count: int
    records: list[LogRecordModel] = Field(default_factory=list)


def _to_model(record: LogRecord) -> LogRecordModel:
    return LogRecordModel(
        ts=record.ts,
        url=record.url,
        final_url=record.final_url,
        host=record.host,
        tier=record.tier,
        status=record.status,
        verdict=record.verdict,
        cache=record.cache,
        total_ms=record.total_ms,
        content_chars=record.content_chars,
        title=record.title,
        error=record.error,
        diagnostics=list(record.diagnostics),
    )


def _narrative(record: LogRecord) -> str:
    """One-liner re-rendered from a record's diagnostics + outcome."""
    if record.status == "ok":
        return f"{record.tier} → ok ({record.total_ms}ms; {record.content_chars} chars)"
    return f"{record.tier} → {record.verdict} ({record.total_ms}ms)"


class LogsRouter(a2kit.Router):
    """Read-only access to the NDJSON request log. CLI: `a2web logs <tool>`."""

    @a2kit.read()
    async def replay(self, *, url: str) -> LogReplayResponse:
        """Return the last log record for a given URL."""
        record = await asyncio.to_thread(find_last_for_url, url)
        if record is None:
            return LogReplayResponse(found=False)
        return LogReplayResponse(
            found=True,
            record=_to_model(record),
            narrative=_narrative(record),
        )

    @a2kit.read()
    async def tail(self, *, n: int = 20, since: str | None = None) -> LogTailResponse:
        """Last `n` records, optionally limited to a duration window (e.g. "1h", "7d")."""
        delta = parse_duration(since) if since else None
        records = await asyncio.to_thread(tail_records, n=n, since=delta)
        return LogTailResponse(count=len(records), records=[_to_model(r) for r in records])

    @a2kit.read()
    async def grep(self, *, pattern: str, n: int = 50) -> LogGrepResponse:
        """Case-insensitive substring search across log records (newest-first)."""
        records = await asyncio.to_thread(grep_records, pattern, limit=n)
        return LogGrepResponse(count=len(records), records=[_to_model(r) for r in records])
