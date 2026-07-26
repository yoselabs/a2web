"""a2web's own logging surface — typed events on stdlib `logging`.

One logger (`"a2web"`), one record shape, two emission surfaces:

- `await info(...)` / `debug` / `warning` / `error` — the async front door for
  pipeline code. Emits one `LogRecord` **and** forwards to the MCP client as a
  `notifications/message` frame when a call is in flight.
- `log_info(...)` / `log_debug` / `log_warning` / `log_error` — the synchronous
  half, for boot, registries and pure functions that cannot `await` and have no
  client to stream to. Identical record shape, no wire forward.

A typed instance IS the payload: `await info(TierStarted(...))` produces a
record whose `getMessage()` is `"TierStarted"` and whose fields ride on
`record.fields`. A plain string first argument is the message, with `**fields`
as the payload.

## Why the front door is async

It is async for exactly one reason: the MCP wire forward is an inline
`await ctx.log(...)`, so a long fetch streams its progress *during* the call
rather than after it. The a2kit sunset originally planned to make emission
synchronous, on the theory that the async-ness was framework ceremony. The wire
goldens (`tests/contracts/wire/notifications.json`) disproved that — fifteen
frames stream per `query` call today. A sync emitter cannot await, and a
`logging.Handler` that schedules the forward as a task loses ordering and can
outlive the call scope it belongs to. So the plan was corrected, not the code:
the async surface stays and the framework is what leaves.

## Ordering and safety

The stdlib record is emitted first and drives the sync handlers (OTel, the
bench live sink). The wire forward is awaited after, and only above
`_WIRE_LEVEL`. Handlers must isolate their own failures (`IsolatingHandler`
below) — a broken sink must never take down the fetch that fed it.

`configure()` sets `propagate = False` and installs a `NullHandler`. This is not
cosmetic: a2web serves MCP over **stdio**, so a record escaping to the root
logger's default stderr writer risks interleaving with the protocol stream. The
logger must never write anywhere it was not explicitly told to.
"""

from __future__ import annotations

import dataclasses
import logging
from enum import Enum
from typing import Any, Literal

LOGGER_NAME = "a2web"

_LOGGER = logging.getLogger(LOGGER_NAME)

#: Failures inside a handler route here. `propagate=False` + a NullHandler stop
#: a failing sink from recursing back through the very handlers that failed.
_FAILURE_LOGGER = logging.getLogger(f"{LOGGER_NAME}.sink_failed")
_FAILURE_LOGGER.propagate = False
if not _FAILURE_LOGGER.handlers:
    _FAILURE_LOGGER.addHandler(logging.NullHandler())

#: MCP log vocabulary.
_MCP_LEVEL: dict[int, Literal["debug", "info", "warning", "error"]] = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
}

#: Minimum level that streams on the MCP wire. The logger itself can sit lower
#: (so a file/OTel sink still sees debug); the wire is the one channel that is
#: not a stdlib handler, so its threshold lives here.
_WIRE_LEVEL: int = logging.INFO


def _resolve_payload(msg_or_instance: Any, fields: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve `(msg, fields)` for a string message or a typed instance.

    A typed instance's fields become the payload — via `model_dump` (pydantic),
    `dataclasses.asdict`, or `vars` — with `Enum` values unwrapped to `.value`
    so the payload is JSON-shaped. Explicit kwargs merge in afterwards and win.
    """
    if isinstance(msg_or_instance, str):
        return msg_or_instance, fields

    instance = msg_or_instance
    if hasattr(instance, "model_dump"):
        payload = instance.model_dump(mode="json")
    elif dataclasses.is_dataclass(instance) and not isinstance(instance, type):
        payload = dataclasses.asdict(instance)
    else:
        try:
            payload = dict(vars(instance))
        except TypeError:
            payload = {}
    payload = {k: (v.value if isinstance(v, Enum) else v) for k, v in payload.items()}
    payload.update(fields)
    return type(instance).__name__, payload


def _emit_record(levelno: int, msg: str, payload: dict[str, Any]) -> None:
    """One record on the `a2web` logger.

    Fields ride a single `fields` attribute rather than being splatted onto the
    record: a flat splat would collide with reserved `LogRecord` attribute names
    (`name`, `msg`, `args`, `levelname`, …) and `logging` raises on the clash.
    """
    _LOGGER.log(levelno, msg, extra={"fields": payload})


def _active_mcp_context() -> Any | None:
    """The in-flight FastMCP `Context`, or None outside a tool call.

    FastMCP keeps this in a contextvar it owns, so a2web does not need a call
    scope of its own. `get_context()` raises when there is none — the CLI path,
    unit tests calling `fetch()` directly, and boot code all land here.
    """
    try:
        from fastmcp.server.dependencies import get_context

        return get_context()
    except (ImportError, RuntimeError, LookupError):
        return None


async def _emit(levelno: int, msg_or_instance: Any, fields: dict[str, Any]) -> None:
    msg, payload = _resolve_payload(msg_or_instance, fields)
    _emit_record(levelno, msg, payload)

    if levelno < _WIRE_LEVEL:
        return
    ctx = _active_mcp_context()
    if ctx is None:
        return
    await ctx.log(level=_MCP_LEVEL.get(levelno, "info"), message=msg, extra=payload)


async def debug(__msg: Any, /, **fields: Any) -> None:
    """Emit a DEBUG record — bulky detail; below the wire threshold by default."""
    await _emit(logging.DEBUG, __msg, dict(fields))


async def info(__msg: Any, /, **fields: Any) -> None:
    """Emit an INFO record — commentary; streams on the wire."""
    await _emit(logging.INFO, __msg, dict(fields))


async def warning(__msg: Any, /, **fields: Any) -> None:
    """Emit a WARNING record; streams on the wire."""
    await _emit(logging.WARNING, __msg, dict(fields))


async def error(__msg: Any, /, **fields: Any) -> None:
    """Emit an ERROR record; streams on the wire."""
    await _emit(logging.ERROR, __msg, dict(fields))


# --------------------------------------------------------------------------- #
# Synchronous half — boot / registry / pure-function sites
# --------------------------------------------------------------------------- #


def log_debug(event: str, /, **fields: Any) -> None:
    """Emit a DEBUG record from sync code."""
    _emit_record(logging.DEBUG, event, dict(fields))


def log_info(event: str, /, **fields: Any) -> None:
    """Emit an INFO record from sync code."""
    _emit_record(logging.INFO, event, dict(fields))


def log_warning(event: str, /, **fields: Any) -> None:
    """Emit a WARNING record from sync code."""
    _emit_record(logging.WARNING, event, dict(fields))


def log_error(event: str, /, **fields: Any) -> None:
    """Emit an ERROR record from sync code."""
    _emit_record(logging.ERROR, event, dict(fields))


# --------------------------------------------------------------------------- #
# Handler isolation
# --------------------------------------------------------------------------- #


class IsolatingHandler(logging.Handler):
    """Base handler whose failures are contained and reported, never raised.

    A sink is a passive observer of the fetch pipeline. If an OTel exporter or a
    bench console dies mid-fetch, the fetch must still complete — a telemetry
    fault becoming a product fault is the wrong trade in every direction.
    Subclasses override `_safe_emit`.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._safe_emit(record)
        except Exception as exc:
            _FAILURE_LOGGER.warning(
                "log handler %s failed on %s: %s: %s",
                type(self).__name__,
                record.getMessage(),
                type(exc).__name__,
                exc,
            )

    def _safe_emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def configure(*, level: str = "info", enabled: bool = True, wire_level: str = "info") -> None:
    """Point the `a2web` logger at its handlers and nowhere else.

    Called once at app boot. Idempotent — safe to call again in tests.

    `enabled=False` is a kill switch: it raises both thresholds above CRITICAL
    rather than detaching handlers, so a sink registered afterwards stays
    silenced too.
    """
    global _WIRE_LEVEL

    _LOGGER.propagate = False
    if not any(isinstance(h, logging.NullHandler) for h in _LOGGER.handlers):
        _LOGGER.addHandler(logging.NullHandler())

    if not enabled:
        _LOGGER.setLevel(logging.CRITICAL + 1)
        _WIRE_LEVEL = logging.CRITICAL + 1
        return

    _LOGGER.setLevel(_LEVELS.get(level, logging.INFO))
    _WIRE_LEVEL = _LEVELS.get(wire_level, logging.INFO)


def add_handler(handler: logging.Handler, *, replace_existing: bool = True) -> None:
    """Attach a sink to the `a2web` logger, replacing any sink of the same type.

    **Replacement is the default because the logger is process-wide and
    `build_app()` is not.** `build_app()` attaches the manifest sinks on every
    call, and it is called repeatedly — once per test, and by any tool that
    builds more than one app in a process. Plain `addHandler` accumulates, so
    the Nth build gives every `*Ended` event N OTel spans. That is a silent
    telemetry corruption: the traces look plausible, they are just multiplied.

    Pass `replace_existing=False` to fan out to several sinks of one type
    deliberately (two exporters, two consoles).
    """
    if replace_existing:
        for existing in [h for h in _LOGGER.handlers if type(h) is type(handler)]:
            _LOGGER.removeHandler(existing)
    _LOGGER.addHandler(handler)


def remove_handler(handler: logging.Handler) -> None:
    """Detach a previously attached sink."""
    _LOGGER.removeHandler(handler)


def get_logger() -> logging.Logger:
    """The `a2web` logger itself.

    For handing to substrate that logs via an *injected* logger (e.g. the
    `plugin-surface` shelf package's `load_surface(..., logger=...)`), so its
    diagnostics land on a2web's single logger — keeping the `propagate=False` +
    NullHandler stdio discipline (MCP is stdio) intact rather than escaping to a
    package-local logger that could write to the root handler.
    """
    return _LOGGER


__all__ = [
    "LOGGER_NAME",
    "IsolatingHandler",
    "add_handler",
    "configure",
    "debug",
    "error",
    "get_logger",
    "info",
    "log_debug",
    "log_error",
    "log_info",
    "log_warning",
    "remove_handler",
    "warning",
]
