"""EventBus + MCP progress sink tests."""

from __future__ import annotations

import anyio
import pytest

from a2web.events import EventBus, StageEnded, StageStarted, TierEnded, TierStarted, mcp_progress_sink
from a2web.models import Verdict


class _RecordingCtx:
    """Minimal ToolContext stub recording event/report_progress calls."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.progress: list[tuple[float, float]] = []

    async def event(self, name: str, **payload: object) -> None:
        self.events.append((name, dict(payload)))

    async def report_progress(self, current: float, total: float) -> None:
        self.progress.append((current, total))


@pytest.mark.asyncio
async def test_publish_without_subscribers_does_not_raise() -> None:
    bus = EventBus()
    await bus.publish(TierStarted(t_ms=0, step="raw"))
    await bus.aclose()


@pytest.mark.asyncio
async def test_two_subscribers_each_receive_published_event() -> None:
    bus = EventBus()
    r1 = bus.subscribe()
    r2 = bus.subscribe()

    received: list[list[str]] = [[], []]

    async def consume(idx: int, recv) -> None:
        async for ev in recv:
            received[idx].append(ev.step)

    async with anyio.create_task_group() as tg:
        tg.start_soon(consume, 0, r1)
        tg.start_soon(consume, 1, r2)
        await bus.publish(TierStarted(t_ms=0, step="raw"))
        await bus.publish(TierEnded(t_ms=0, step="raw", engine=None, verdict=Verdict.ok, dur_ms=10))
        await bus.aclose()

    assert received[0] == ["raw", "raw"]
    assert received[1] == ["raw", "raw"]


@pytest.mark.asyncio
async def test_mcp_progress_sink_records_event_per_published() -> None:
    bus = EventBus()
    recv = bus.subscribe()
    ctx = _RecordingCtx()

    async with anyio.create_task_group() as tg:
        tg.start_soon(mcp_progress_sink, ctx, recv)
        await bus.publish(TierStarted(t_ms=0, step="raw"))
        await bus.publish(TierEnded(t_ms=0, step="raw", engine=None, verdict=Verdict.ok, dur_ms=10))
        await bus.publish(StageStarted(t_ms=10, step="extract"))
        await bus.publish(StageEnded(t_ms=10, step="extract", verdict=Verdict.ok, dur_ms=20))
        await bus.aclose()

    names = [name for name, _ in ctx.events]
    assert names == ["TierStarted", "TierEnded", "StageStarted", "StageEnded"]


@pytest.mark.asyncio
async def test_mcp_progress_sink_reports_progress_only_on_end_events() -> None:
    bus = EventBus()
    recv = bus.subscribe()
    ctx = _RecordingCtx()

    async with anyio.create_task_group() as tg:
        tg.start_soon(mcp_progress_sink, ctx, recv)
        await bus.publish(TierStarted(t_ms=0, step="raw"))
        await bus.publish(TierEnded(t_ms=0, step="raw", engine=None, verdict=Verdict.ok, dur_ms=10))
        await bus.publish(StageStarted(t_ms=10, step="extract"))
        await bus.publish(StageEnded(t_ms=10, step="extract", verdict=Verdict.ok, dur_ms=20))
        await bus.aclose()

    # 4 events published, 2 are End → 2 progress calls
    assert len(ctx.progress) == 2
    assert all(0.0 <= cur <= 1.0 for cur, _ in ctx.progress)
