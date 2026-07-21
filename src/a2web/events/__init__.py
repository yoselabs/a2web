"""Event types + OTel handler for the fetch orchestrator.

Emissions go through stdlib logging:
`await a2web_log.info(EventInstance(...))` from the orchestrator. `a2web.log`
resolves each typed instance to a `logging.LogRecord` (message = type name,
payload on `record.fields`), fans it out to the handlers attached to the
`a2web` logger (our `OtelHandler`, via `a2web.log.add_handler`), and forwards
it to the MCP client as a `notifications/message` frame when a call is in
flight.
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
