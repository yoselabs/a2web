"""OTel handler — registered via `app.log.add_handler(OtelHandler())` in server.py.

Receives a `logging.LogRecord` from a2kit's stdlib-logging emission chain.
Emits one OTel span per `*Ended` event when the SDK is available; degrades
to a silent drain when OTel is absent.

a2kit owns the MCP/CLI bridge — we don't write a ctx-forwarding sink anymore.
The typed payload arrives as `record.a2kit_fields` (the dict a2kit attaches
via `extra={"a2kit_fields": ...}`); the event-type name is `record.getMessage()`.
"""

from __future__ import annotations

import logging
from typing import Any


def _load_tracer() -> Any | None:
    """Lazy-import OTel tracer; return None when SDK absent."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return None
    return trace.get_tracer("a2web")


_TRACER = _load_tracer()


class OtelHandler(logging.Handler):
    """Forward end-of-phase events to OTel as one span per phase.

    Drains every record regardless of OTel availability so the producer
    never blocks. When OTel is missing, `emit` is effectively a no-op.
    Only `*Ended` events become spans; `*Started` and `TierHeartbeat` events
    are consumed silently (they're for live observability, not historical
    trace data).
    """

    def emit(self, record: logging.LogRecord) -> None:
        if _TRACER is None:
            return
        name = record.getMessage()
        if not name.endswith("Ended"):
            return
        payload: dict[str, Any] = getattr(record, "a2kit_fields", {}) or {}
        step = payload.get("step", "unknown")
        span = _TRACER.start_span(f"a2web.{step}")
        try:
            span.set_attribute("a2web.step", step)
            if "verdict" in payload:
                span.set_attribute("a2web.verdict", str(payload["verdict"]))
            if "dur_ms" in payload:
                span.set_attribute("a2web.dur_ms", int(payload["dur_ms"]))
            if "t_ms" in payload:
                span.set_attribute("a2web.t_ms", int(payload["t_ms"]))
        finally:
            span.end()
