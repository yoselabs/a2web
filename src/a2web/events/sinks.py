"""Event sinks — consumers of the diagnostic event bus.

PR6 ships the MCP progress sink. PR7 will add an OTel sink subscribed to
the same bus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..utils.time import fmt_dur
from .types import Event, StageEnded, TierEnded

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectReceiveStream


class _ProgressCtx(Protocol):
    """Duck-typed against a2kit's ToolContext."""

    async def event(self, name: str, **payload: object) -> None: ...

    async def report_progress(self, current: float, total: float | None = None) -> None: ...


def _progress_for(event: Event) -> float:
    """Estimate progress per `v0.1-response-format.md` §3."""
    if isinstance(event, TierEnded):
        if event.step == "site_handler":
            return 0.7
        if event.step == "raw":
            return 0.7
        return 0.6
    if isinstance(event, StageEnded):
        if event.step == "extract":
            return 0.85
        if event.step == "fit":
            return 0.95
        if event.step == "gate":
            return 0.97
        if event.step == "cache_write":
            return 1.0
    return 0.5


def _message_for(event: Event) -> str:
    if isinstance(event, TierEnded):
        return f"{event.step} → {event.verdict.value} ({fmt_dur(event.dur_ms)})"
    if isinstance(event, StageEnded):
        return f"{event.step} → {event.verdict.value} ({fmt_dur(event.dur_ms)})"
    return event.step


def _payload(event: Event) -> dict[str, object]:
    """Flat payload for `ctx.event(name, **payload)`. No nested dicts."""
    out: dict[str, object] = {"t_ms": event.t_ms, "step": event.step}
    if isinstance(event, TierEnded | StageEnded):
        out["verdict"] = event.verdict.value
        out["dur_ms"] = event.dur_ms
    return out


async def mcp_progress_sink(ctx: _ProgressCtx, recv: MemoryObjectReceiveStream[Event]) -> None:
    """Forward events to a ToolContext as ctx.event + ctx.report_progress.

    `ctx` is duck-typed against a2kit's `ToolContext` interface (`ctx.event`,
    `ctx.report_progress`). End events also fire a progress update.
    """
    async for event in recv:
        payload = _payload(event)
        if isinstance(event, TierEnded | StageEnded):
            payload["message"] = _message_for(event)
        await ctx.event(event.__class__.__name__, **payload)
        if isinstance(event, TierEnded | StageEnded):
            # `ctx.report_progress(current, total=None)` — current=progress,
            # total=1.0 normalizes to a percentage in MCP/CLI rendering.
            await ctx.report_progress(_progress_for(event), 1.0)
