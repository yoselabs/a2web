"""OtelHandler unit tests — feed synthetic LogRecords, assert span behavior."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from a2web.events import OtelHandler


def _make_record(name: str, payload: dict[str, Any]) -> logging.LogRecord:
    """Build a LogRecord shaped like a2kit's typed-event emission.

    `getMessage()` returns the event-type name; the payload rides on
    `record.a2kit_fields` (a2kit attaches it via `extra={"a2kit_fields": ...}`).
    """
    record = logging.LogRecord("a2kit", logging.INFO, __file__, 0, name, None, None)
    record.a2kit_fields = payload  # type: ignore[attr-defined]
    return record


def test_ended_event_creates_span(monkeypatch: pytest.MonkeyPatch) -> None:
    span = MagicMock()
    tracer = MagicMock()
    tracer.start_span.return_value = span
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    record = _make_record("TierEnded", {"step": "raw", "verdict": "ok", "dur_ms": 420, "t_ms": 0})
    OtelHandler().emit(record)

    tracer.start_span.assert_called_once_with("a2web.raw")
    span.set_attribute.assert_any_call("a2web.step", "raw")
    span.set_attribute.assert_any_call("a2web.verdict", "ok")
    span.set_attribute.assert_any_call("a2web.dur_ms", 420)
    span.set_attribute.assert_any_call("a2web.t_ms", 0)
    span.end.assert_called_once()


def test_started_event_does_not_create_span(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = MagicMock()
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    record = _make_record("TierStarted", {"step": "raw", "t_ms": 0})
    OtelHandler().emit(record)

    tracer.start_span.assert_not_called()


def test_heartbeat_does_not_create_span(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = MagicMock()
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    record = _make_record("TierHeartbeat", {"step": "browser", "elapsed_in_tier_ms": 2000, "t_ms": 2000})
    OtelHandler().emit(record)

    tracer.start_span.assert_not_called()


def test_no_tracer_drains_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("a2web.events.sinks._TRACER", None)

    record = _make_record("TierEnded", {"step": "raw", "verdict": "ok", "dur_ms": 1, "t_ms": 0})
    OtelHandler().emit(record)  # no exception, returns None
