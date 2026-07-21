"""Capture records emitted on the managed `a2web` logger.

Two shapes, both attaching a handler **directly** to the `a2web` logger:

- `capture_logs()` yields `{"event": <message>, **<fields>}` dicts — the shape
  the old structlog capture produced, so field-key assertions read naturally.
- `capture_log_records()` yields raw `LogRecord`s — a drop-in for
  `caplog.records`.

## Why not pytest's `caplog`

`caplog` installs its handler on the **root** logger and relies on records
propagating up to it. `a2web.log.configure()` sets `propagate = False` on the
`a2web` logger, deliberately: a2web serves MCP over stdio, and a record
escaping to the root logger's default stderr writer can interleave with the
protocol stream. Production must not propagate.

That made `caplog`-based tests order-dependent in the worst way — they passed
alone and failed in a full run, because `configure()` only fires inside
`build_app()`, so whether propagation was still on depended on which tests had
run first. Attaching to the logger directly is immune to that, and it observes
exactly the records the real sinks receive.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

from a2web.log import LOGGER_NAME


@contextlib.contextmanager
def _attached(handler: logging.Handler) -> Iterator[None]:
    """Attach `handler` to the `a2web` logger at DEBUG, restoring level after."""
    logger = logging.getLogger(LOGGER_NAME)
    handler.setLevel(logging.DEBUG)
    prev_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


@contextlib.contextmanager
def capture_logs() -> Iterator[list[dict[str, Any]]]:
    """Yield a growing list of `{"event": msg, **fields}` dicts."""
    records: list[dict[str, Any]] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            fields = getattr(record, "fields", {}) or {}
            records.append({"event": record.getMessage(), **fields})

    with _attached(_Capture()):
        yield records


@contextlib.contextmanager
def capture_log_records() -> Iterator[list[logging.LogRecord]]:
    """Yield a growing list of raw `LogRecord`s — drop-in for `caplog.records`."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    with _attached(_Capture()):
        yield records
