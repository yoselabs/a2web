"""Capture records emitted on the managed `a2kit` logger as plain dicts.

Drop-in replacement for `structlog.testing.capture_logs` now that a2web emits
through the a2kit-managed channel. Each captured record is normalized to the
same dict shape the old structlog capture produced: ``{"event": <message>,
**<structured fields>}`` — so existing assertions on ``r.get("event")`` and
field keys keep working unchanged.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any


@contextlib.contextmanager
def capture_a2kit_logs() -> Iterator[list[dict[str, Any]]]:
    """Yield a growing list of `{"event": msg, **a2kit_fields}` dicts for every
    record emitted on the `a2kit` logger inside the block."""
    records: list[dict[str, Any]] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            fields = getattr(record, "a2kit_fields", {}) or {}
            records.append({"event": record.getMessage(), **fields})

    logger = logging.getLogger("a2kit")
    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prev_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
