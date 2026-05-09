"""LogRecord shape + from_response derivation."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

from a2web.log.record import LogRecord, from_response
from a2web.models import (
    CacheState,
    Confidence,
    Diagnostic,
    FetchResponse,
    FetchStatus,
    Verdict,
)


def test_logrecord_is_dataclass_with_slots() -> None:
    assert dataclasses.is_dataclass(LogRecord)
    assert LogRecord.__slots__


def test_to_json_is_single_line_and_parseable() -> None:
    rec = LogRecord(
        ts="2026-05-09T19:00:00.000+00:00",
        url="https://example.com",
        final_url="https://example.com/",
        host="example.com",
        tier="raw",
        status="ok",
        verdict="ok",
        cache="miss",
        total_ms=200,
        content_chars=1500,
    )
    line = rec.to_json()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["url"] == "https://example.com"
    assert parsed["total_ms"] == 200


def test_from_response_compresses_diagnostics() -> None:
    response = FetchResponse(
        url="https://example.org/post",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.high,
        started_at=datetime.now(UTC),
        total_ms=350,
        cache=CacheState.miss,
        title="Hello",
        content_md="x" * 2000,
        diagnostics=[
            Diagnostic(t_ms=0, step="raw", verdict=Verdict.ok, dur_ms=120),
            Diagnostic(t_ms=120, step="extract", verdict=Verdict.ok, dur_ms=80),
            Diagnostic(t_ms=200, step="gate", verdict=Verdict.ok, dur_ms=2),
        ],
    )
    rec = from_response(response, input_url="https://example.org/post?utm=1")
    assert rec.url == "https://example.org/post?utm=1"
    assert rec.final_url == "https://example.org/post"
    assert rec.host == "example.org"
    assert rec.status == "ok"
    assert rec.verdict == "ok"
    assert rec.tier == "raw"
    assert rec.content_chars == 2000
    assert all(set(d) == {"step", "verdict", "dur_ms"} for d in rec.diagnostics)
    assert rec.title == "Hello"


def test_from_response_picks_dominant_non_ok_verdict() -> None:
    response = FetchResponse(
        url="https://blocked.example/",
        status=FetchStatus.failed,
        tier="raw",
        confidence=Confidence.low,
        started_at=datetime.now(UTC),
        total_ms=500,
        cache=CacheState.miss,
        diagnostics=[
            Diagnostic(t_ms=0, step="raw", verdict=Verdict.ok, dur_ms=120),
            Diagnostic(t_ms=120, step="extract", verdict=Verdict.ok, dur_ms=80),
            Diagnostic(t_ms=200, step="gate", verdict=Verdict.block_page_detected, dur_ms=2),
        ],
    )
    rec = from_response(response)
    assert rec.verdict == "block_page_detected"
