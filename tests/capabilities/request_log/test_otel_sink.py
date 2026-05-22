"""otel_sink unit tests — feed synthetic LddEmission, assert span behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from a2web.events import otel_sink


def _make_emission(name: str, payload: dict[str, Any]) -> Any:
    """Build a duck-typed LddEmission with the fields otel_sink reads."""
    e = MagicMock()
    e.name = name
    e.payload = payload
    return e


@pytest.mark.asyncio
async def test_ended_event_creates_span(monkeypatch: pytest.MonkeyPatch) -> None:
    span = MagicMock()
    tracer = MagicMock()
    tracer.start_span.return_value = span
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    emission = _make_emission("TierEnded", {"step": "raw", "verdict": "ok", "dur_ms": 420, "t_ms": 0})
    await otel_sink(emission)

    tracer.start_span.assert_called_once_with("a2web.raw")
    span.set_attribute.assert_any_call("a2web.step", "raw")
    span.set_attribute.assert_any_call("a2web.verdict", "ok")
    span.set_attribute.assert_any_call("a2web.dur_ms", 420)
    span.set_attribute.assert_any_call("a2web.t_ms", 0)
    span.end.assert_called_once()


@pytest.mark.asyncio
async def test_started_event_does_not_create_span(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = MagicMock()
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    emission = _make_emission("TierStarted", {"step": "raw", "t_ms": 0})
    await otel_sink(emission)

    tracer.start_span.assert_not_called()


@pytest.mark.asyncio
async def test_heartbeat_does_not_create_span(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = MagicMock()
    monkeypatch.setattr("a2web.events.sinks._TRACER", tracer)

    emission = _make_emission("TierHeartbeat", {"step": "browser", "elapsed_in_tier_ms": 2000, "t_ms": 2000})
    await otel_sink(emission)

    tracer.start_span.assert_not_called()


@pytest.mark.asyncio
async def test_no_tracer_drains_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("a2web.events.sinks._TRACER", None)

    emission = _make_emission("TierEnded", {"step": "raw", "verdict": "ok", "dur_ms": 1, "t_ms": 0})
    await otel_sink(emission)  # no exception, returns None
