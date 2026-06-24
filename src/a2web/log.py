"""Synchronous emit helpers for the a2kit-managed logging channel.

a2web's async code paths emit via ``await a2kit.log.{debug,info,warning,error}``.
Synchronous boot / registry / pure-function call sites cannot ``await`` and have
no active call scope, so they use these thin wrappers instead: one stdlib
``LogRecord`` on the ``a2kit`` logger with the structured payload riding on
``record.a2kit_fields`` — field-shape-identical to the async front door's
synchronous half (``a2kit.packages.log.emission._emit``).

The only thing the async path adds is the MCP-wire forward, which fires solely
under an active fastmcp Context. Sync boot code has no such scope, so it loses
nothing by going straight to the logger. All records remain governed by
``LogConfig`` (level / wire_level / stderr_sink / enabled).
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger("a2kit")


def _emit(levelno: int, event: str, fields: dict[str, Any]) -> None:
    _LOGGER.log(levelno, event, extra={"a2kit_fields": fields})


def log_debug(event: str, /, **fields: Any) -> None:
    """Emit a DEBUG record on the ``a2kit`` logger (file-only by default level)."""
    _emit(logging.DEBUG, event, dict(fields))


def log_info(event: str, /, **fields: Any) -> None:
    """Emit an INFO record on the ``a2kit`` logger."""
    _emit(logging.INFO, event, dict(fields))


def log_warning(event: str, /, **fields: Any) -> None:
    """Emit a WARNING record on the ``a2kit`` logger."""
    _emit(logging.WARNING, event, dict(fields))


def log_error(event: str, /, **fields: Any) -> None:
    """Emit an ERROR record on the ``a2kit`` logger."""
    _emit(logging.ERROR, event, dict(fields))


__all__ = ["log_debug", "log_error", "log_info", "log_warning"]
