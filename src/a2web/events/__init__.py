"""Diagnostic event bus — single producer (orchestrator), pluggable sinks.

The bus is opt-in: when `fetcher.fetch(url, *, state)` is called without a
`bus=` kwarg, no events are published. The router builds a bus per call,
attaches the MCP progress sink, and threads it into the orchestrator.
PR7 will add an OTel sink subscribed to the same bus.
"""

from __future__ import annotations

from .bus import EventBus
from .sinks import mcp_progress_sink
from .types import Event, StageEnded, StageStarted, TierEnded, TierStarted

__all__ = [
    "Event",
    "EventBus",
    "StageEnded",
    "StageStarted",
    "TierEnded",
    "TierStarted",
    "mcp_progress_sink",
]
