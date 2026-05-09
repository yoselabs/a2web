"""OTel sink tests — span emission, lazy import drain."""

from __future__ import annotations

import sys
from typing import Any

import anyio
import pytest

from a2web.events import EventBus, otel_sink
from a2web.events.types import StageEnded, StageStarted, TierEnded, TierStarted
from a2web.models import Verdict


class _FakeSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attrs: dict[str, Any] = {}
        self.ended = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def end(self) -> None:
        self.ended = True


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_span(self, name: str) -> _FakeSpan:
        span = _FakeSpan(name)
        self.spans.append(span)
        return span


@pytest.mark.asyncio
async def test_otel_sink_emits_span_per_end_event(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = _FakeTracer()
    monkeypatch.setattr("a2web.events.sinks._load_tracer", lambda: tracer)

    bus = EventBus()
    recv = bus.subscribe()

    async with anyio.create_task_group() as tg:
        tg.start_soon(otel_sink, recv)
        await bus.publish(TierStarted(t_ms=0, step="raw", host="example.com"))
        await bus.publish(TierEnded(t_ms=10, step="raw", engine="curl_cffi", verdict=Verdict.ok, dur_ms=10))
        await bus.publish(StageStarted(t_ms=15, step="extract"))
        await bus.publish(StageEnded(t_ms=20, step="extract", verdict=Verdict.ok, dur_ms=5))
        await bus.aclose()

    assert [s.name for s in tracer.spans] == ["a2web.raw", "a2web.extract"]
    assert tracer.spans[0].attrs == {
        "a2web.step": "raw",
        "a2web.verdict": "ok",
        "a2web.dur_ms": 10,
        "a2web.t_ms": 10,
    }
    assert all(s.ended for s in tracer.spans)


@pytest.mark.asyncio
async def test_otel_sink_drains_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When `_load_tracer` returns None, sink consumes the stream silently."""
    monkeypatch.setattr("a2web.events.sinks._load_tracer", lambda: None)

    bus = EventBus()
    recv = bus.subscribe()

    async with anyio.create_task_group() as tg:
        tg.start_soon(otel_sink, recv)
        await bus.publish(TierEnded(t_ms=0, step="raw", engine="curl_cffi", verdict=Verdict.ok, dur_ms=10))
        await bus.aclose()


def test_load_tracer_returns_none_when_module_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ImportError on `from opentelemetry import trace` and ensure None."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("forced")
        return real_import(name, *args, **kwargs)

    # Pop cached module so the import inside _load_tracer re-runs.
    for mod in list(sys.modules):
        if mod == "opentelemetry" or mod.startswith("opentelemetry."):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    monkeypatch.setattr("builtins.__import__", fake_import)

    from a2web.events.sinks import _load_tracer

    assert _load_tracer() is None
