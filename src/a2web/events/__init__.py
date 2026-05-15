"""Event types + OTel sink for the fetch orchestrator.

Emissions go through a2kit.ldd (`await a2kit.ldd.event(EventInstance(...))`)
from the orchestrator with ctx bound ambient by the dispatcher; a2kit fans
them out to subscribed sinks (the FastMCP wire bridge plus our `otel_sink`
registered via `app.ldd.add_sink`).
"""

from .sinks import otel_sink
from .types import (
    Event,
    StageEnded,
    StageStarted,
    TierEnded,
    TierHeartbeat,
    TierStarted,
)

__all__ = [
    "Event",
    "StageEnded",
    "StageStarted",
    "TierEnded",
    "TierHeartbeat",
    "TierStarted",
    "otel_sink",
]
