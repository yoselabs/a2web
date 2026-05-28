"""OTel sink — registered via `app.ldd.add_sink(otel_sink)` in server.py.

Receives `LddEmission` from a2kit's emission chain (sequential fan-out after
the FastMCP wire emit). Emits one OTel span per `*Ended` event when the SDK
is available; degrades to a silent drain when OTel is absent.

a2kit owns the MCP/CLI bridge — we don't write a ctx-forwarding sink anymore.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit import LddEmission


def _load_tracer() -> Any | None:
    """Lazy-import OTel tracer; return None when SDK absent."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return None
    return trace.get_tracer("a2web")


_TRACER = _load_tracer()


async def otel_sink(emission: LddEmission) -> None:
    """Forward end-of-phase events to OTel as one span per phase.

    Drains every emission regardless of OTel availability so the producer
    never blocks. When OTel is missing, this is effectively a no-op consumer.
    Only `*Ended` events become spans; `*Started` and `TierHeartbeat` events
    are consumed silently (they're for live observability, not historical
    trace data).
    """
    if _TRACER is None:
        return
    name = emission.name
    if not name.endswith("Ended"):
        return
    payload = emission.payload
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
