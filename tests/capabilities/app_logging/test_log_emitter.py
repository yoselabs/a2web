"""`a2web.log` — the emitter a2web owns after the a2kit sunset's Phase 1.

Three properties are load-bearing enough to pin here, over and above the
record-shape checks in `test_log_helper.py`:

1. **The logger never writes anywhere it was not told to.** a2web serves MCP
   over stdio; a record reaching the root logger's default stderr writer can
   interleave with the protocol stream.
2. **A sink cannot kill the pipeline that feeds it.** Telemetry observes the
   fetch, it does not gate it.
3. **The wire forward degrades to nothing outside a call**, so the same emit
   call works from the CLI, from a unit test, and mid-dispatch.

The wire forward's *positive* case — that frames actually reach a client — is
covered where it belongs, against a real `fastmcp.Client`, in
`tests/contracts/test_wire_contract.py::test_wire_notifications`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from a2web import log as a2web_log
from a2web.events import OtelHandler, StageEnded
from a2web.log import LOGGER_NAME, IsolatingHandler, configure, info, log_info
from a2web.models import Verdict
from tests._helpers.log_capture import capture_log_records


@dataclass(slots=True)
class _Dataclassy:
    step: str
    verdict: Verdict


class _Pydanticky(BaseModel):
    step: str
    count: int


# ------------------------------------------------------------------ #
# Payload resolution
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_dataclass_instance_becomes_message_plus_fields() -> None:
    with capture_log_records() as records:
        await info(_Dataclassy(step="gate", verdict=Verdict.ok))

    assert len(records) == 1
    assert records[0].getMessage() == "_Dataclassy"
    # Enum values are unwrapped so the payload is JSON-shaped for any sink.
    assert records[0].fields == {"step": "gate", "verdict": "ok"}


@pytest.mark.asyncio
async def test_pydantic_instance_becomes_message_plus_fields() -> None:
    with capture_log_records() as records:
        await info(_Pydanticky(step="extract", count=3))

    assert records[0].getMessage() == "_Pydanticky"
    assert records[0].fields == {"step": "extract", "count": 3}


@pytest.mark.asyncio
async def test_explicit_kwargs_merge_over_instance_fields() -> None:
    with capture_log_records() as records:
        await info(_Pydanticky(step="extract", count=3), count=99, host="example.org")

    assert records[0].fields == {"step": "extract", "count": 99, "host": "example.org"}


@pytest.mark.asyncio
async def test_string_message_keeps_kwargs_as_payload() -> None:
    with capture_log_records() as records:
        await info("other_pages_suggested", url="https://example.org", count=2)

    assert records[0].getMessage() == "other_pages_suggested"
    assert records[0].fields == {"url": "https://example.org", "count": 2}


def test_fields_ride_one_attribute_not_splatted_onto_the_record() -> None:
    """A flat splat would collide with reserved `LogRecord` attribute names
    (`name`, `msg`, `args`, `levelname`) and `logging` raises on the clash. The
    single-dict carrier is what makes `name=` a safe field key."""
    with capture_log_records() as records:
        log_info("plugin_unavailable", name="anthropic", msg="shadowed", args="also shadowed")

    record = records[0]
    assert record.name == LOGGER_NAME  # NOT "anthropic"
    assert record.getMessage() == "plugin_unavailable"  # NOT "shadowed"
    assert record.fields == {"name": "anthropic", "msg": "shadowed", "args": "also shadowed"}


# ------------------------------------------------------------------ #
# Property 1 — the logger writes only where it was told to
# ------------------------------------------------------------------ #


def test_configure_stops_propagation_to_root(caplog: pytest.LogCaptureFixture) -> None:
    """The MCP-stdio safety property.

    `caplog` captures via the ROOT logger, so its blindness here IS the
    assertion: after `configure()`, nothing escapes upward to whatever the root
    logger happens to be writing to.
    """
    configure()
    logger = logging.getLogger(LOGGER_NAME)

    assert logger.propagate is False
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers), (
        "a logger with no handlers falls back to logging.lastResort, which writes to stderr"
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        log_info("must_not_reach_root")
    assert not [r for r in caplog.records if r.getMessage() == "must_not_reach_root"]


def test_configure_is_idempotent() -> None:
    configure()
    before = len(logging.getLogger(LOGGER_NAME).handlers)
    configure()
    configure()
    assert len(logging.getLogger(LOGGER_NAME).handlers) == before


def test_disabled_silences_records_and_the_wire() -> None:
    """`enabled=False` raises thresholds rather than detaching handlers, so a
    sink registered after the kill switch stays silenced too."""
    try:
        configure(enabled=False)
        records: list[logging.LogRecord] = []

        class _Late(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Late()
        a2web_log.add_handler(handler)
        try:
            log_info("suppressed")
            assert records == []
        finally:
            a2web_log.remove_handler(handler)
    finally:
        configure()  # restore for the rest of the session


# ------------------------------------------------------------------ #
# Property 2 — a sink cannot kill its producer
# ------------------------------------------------------------------ #


class _ExplodingHandler(IsolatingHandler):
    def _safe_emit(self, record: logging.LogRecord) -> None:
        raise RuntimeError("exporter is down")


@pytest.mark.asyncio
async def test_a_failing_sink_does_not_reach_the_producer() -> None:
    handler = _ExplodingHandler()
    a2web_log.add_handler(handler)
    try:
        # Must not raise, and must not print a logging-internal traceback.
        await info(_Dataclassy(step="gate", verdict=Verdict.ok))
    finally:
        a2web_log.remove_handler(handler)


@pytest.mark.asyncio
async def test_a_failing_sink_does_not_starve_its_siblings() -> None:
    """Containment is per-handler: the one that raised is skipped, the rest of
    the fan-out still runs. A sink dying must not blind the others."""
    seen: list[str] = []

    class _Good(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.getMessage())

    bad, good = _ExplodingHandler(), _Good()
    a2web_log.add_handler(bad)
    a2web_log.add_handler(good)
    try:
        await info(_Dataclassy(step="gate", verdict=Verdict.ok))
    finally:
        a2web_log.remove_handler(bad)
        a2web_log.remove_handler(good)

    assert seen == ["_Dataclassy"]


# ------------------------------------------------------------------ #
# Property 3 — no ambient call scope required
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_emit_outside_a_tool_call_is_a_plain_record() -> None:
    """No FastMCP context is active here — the direct-`fetch()` path, the CLI,
    and boot code all look like this. The forward must simply not happen; it
    must not raise, and it must not suppress the stdlib record."""
    with capture_log_records() as records:
        await info("no_context_here", k="v")

    assert [r.getMessage() for r in records] == ["no_context_here"]


# ------------------------------------------------------------------ #
# Task 1.6 — exactly one OTel span per *Ended event
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_one_otel_span_per_ended_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression for the double emission.

    a2kit attaches its own generic `OtelHandler` at boot (`otel_sink="auto"`),
    so while a2web's records rode the `a2kit` logger every `*Ended` event
    produced two spans. Moving to a2web's own logger dissolved that
    structurally. This pins it: a2web attaches exactly one OTel handler, and one
    `*Ended` event yields exactly one span.
    """
    spans: list[str] = []

    class _Span:
        def set_attribute(self, *_args: object) -> None: ...
        def end(self) -> None: ...

    class _Tracer:
        def start_span(self, name: str) -> _Span:
            spans.append(name)
            return _Span()

    monkeypatch.setattr("a2web.events.sinks._TRACER", _Tracer())

    handler = OtelHandler()
    a2web_log.add_handler(handler)
    try:
        await info(StageEnded(t_ms=0, step="gate", verdict=Verdict.ok, dur_ms=1))
    finally:
        a2web_log.remove_handler(handler)

    assert spans == ["a2web.gate"], f"expected exactly one span, got {spans}"


@pytest.mark.asyncio
async def test_started_events_produce_no_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-vacuity for the test above: if the handler spanned everything, the
    single-span assertion would pass for the wrong reason."""
    spans: list[str] = []

    class _Tracer:
        def start_span(self, name: str) -> object:
            spans.append(name)
            raise AssertionError("should not be reached")

    monkeypatch.setattr("a2web.events.sinks._TRACER", _Tracer())

    handler = OtelHandler()
    a2web_log.add_handler(handler)
    try:
        await info("StageStarted", step="gate", t_ms=0)
    finally:
        a2web_log.remove_handler(handler)

    assert spans == []
