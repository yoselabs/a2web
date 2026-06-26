"""Event types + OTel handler for the fetch orchestrator.

Emissions go through stdlib logging:
`await a2kit.log.info(EventInstance(...))` from the orchestrator. a2kit
resolves each typed instance to a `logging.LogRecord` (message = type name,
payload on `record.a2kit_fields`) and fans it out to the handlers attached
to the `a2kit` logger — the FastMCP wire bridge plus our `OtelHandler`
(attached via `app.log.add_handler`).
"""

from .sinks import OtelHandler
from .types import (
    BrowserSubprocessStderr,
    Event,
    StageEnded,
    StageStarted,
    TierEnded,
    TierHeartbeat,
    TierStarted,
)

__all__ = [
    "BrowserSubprocessStderr",
    "Event",
    "OtelHandler",
    "StageEnded",
    "StageStarted",
    "TierEnded",
    "TierHeartbeat",
    "TierStarted",
]
