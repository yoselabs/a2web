"""OTel handler — attached to the `a2web` logger in `server.py`.

Receives a `logging.LogRecord` from `a2web.log`'s emission chain: the
event-type name is `record.getMessage()`, the typed payload rides on
`record.fields`. Emits one OTel span per `*Ended` event when the SDK is
available; degrades to a silent drain when OTel is absent.

The MCP wire forward is deliberately NOT a handler — it stays an inline
`await ctx.log(...)` inside `a2web.log._emit` so a long fetch streams live,
mid-call, rather than being deferred behind a sync handler.

**On the former double emission.** a2kit ships its own generic `OtelHandler`
and attaches it at boot whenever `LogConfig.otel_sink="auto"` (the default),
so every `*Ended` event used to produce two spans: a2kit's, named after the
event with `a2kit.*` attributes, and this one, named `a2web.<step>` with
`a2web.*` attributes. Moving a2web's records onto their own logger dissolved
the duplication structurally — a2kit's handler sits on the `a2kit` logger and
no longer sees them. Nothing had to be disabled, which is the better kind of
fix: there is no configuration left to get wrong.
"""

from __future__ import annotations

import logging
from typing import Any

from ..log import IsolatingHandler


def _load_tracer() -> Any | None:
    """Lazy-import OTel tracer; return None when SDK absent."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return None
    return trace.get_tracer("a2web")


_TRACER = _load_tracer()


class OtelHandler(IsolatingHandler):
    """Forward end-of-phase events to OTel as one span per phase.

    Drains every record regardless of OTel availability so the producer
    never blocks. When OTel is missing, emission is effectively a no-op.
    Only `*Ended` events become spans; `*Started` and `TierHeartbeat` events
    are consumed silently (they're for live observability, not historical
    trace data).

    Isolated by its base class: an exporter that raises mid-fetch (a dead
    collector, a serialization fault on an odd attribute) must not take the
    fetch down with it. Telemetry observes the pipeline; it does not gate it.
    """

    def _safe_emit(self, record: logging.LogRecord) -> None:
        if _TRACER is None:
            return
        name = record.getMessage()
        if not name.endswith("Ended"):
            return
        payload: dict[str, Any] = getattr(record, "fields", {}) or {}
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
