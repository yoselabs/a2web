"""Opt-in failure-feedback reporting (openspec `add-a2web-feedback-channel`,
extended by `unify-otel-telemetry-seam`).

Offline unit tests directly against `_record_feedback` — no App, no real fetch,
no network. `AppState.breakers`/`proxy_pool`/`sqlite` are not read by the
function under test, so `None` stand-ins are enough (this module is not
type-checked by `make ty`, which scopes to `src/` only).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from a2web.decision_log import Observation, ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.pipeline import _record_feedback
from a2web.hints import OperatorHint
from a2web.models import CacheState, Confidence, FetchResponse, FetchStatus, Verdict
from a2web.settings import AppSettings
from a2web.state import AppState

_RealAsyncClient = httpx.AsyncClient


def _response(*, status: FetchStatus = FetchStatus.failed, confidence: Confidence = Confidence.low) -> FetchResponse:
    return FetchResponse(url="https://example.com/page", status=status, tier="browser", confidence=confidence)


def _fc(
    *,
    hints: list[OperatorHint],
    ask: str | None = None,
    url: str = "https://example.com/page",
    final_url: str | None = None,
    requested_url: str | None = None,
    observations: list[Observation] | None = None,
) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=time.perf_counter(),
            profile_hash="test",
            bypass_cache=True,
            ask=ask,
            requested_url=requested_url if requested_url is not None else url,
        ),
        resources=FetchResources(sqlite=None),
        url=url,
        final_url=final_url if final_url is not None else url,
    )
    fc.operator_hints.extend(hints)
    fc.status_code = 403
    fc.content_type = "text/html"
    fc.cache_state = CacheState.miss
    fc.tier_used = "browser"
    default_observation = Observation(
        kind=ObservationKind.tier_outcome, source="browser", verdict=Verdict.block_page_detected, authoritative=True, t_ms=10
    )
    fc.observations.extend(observations if observations is not None else [default_observation])
    return fc


def _state(**settings_kwargs: Any) -> AppState:
    return AppState(
        settings=AppSettings(**settings_kwargs),
        breakers=None,  # type: ignore[arg-type]
        proxy_pool=None,  # type: ignore[arg-type]
        sqlite=None,  # type: ignore[arg-type]
    )


class _RecordingTransport(httpx.MockTransport):
    """Captures every request it handles instead of hitting the network."""

    def __init__(self, response: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return response

        super().__init__(handler)


class _FailingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")


@pytest.fixture
def critical_hint() -> OperatorHint:
    return OperatorHint(code="try_user_browser", message="Walled off.", severity="critical")


@pytest.fixture
def info_hint() -> OperatorHint:
    return OperatorHint(code="listing_partial", message="Partial listing.", severity="info")


@pytest.fixture
def url_bearing_hint() -> OperatorHint:
    return OperatorHint(
        code="try_user_browser",
        message="This URL was NOT retrieved — it is behind an anti-bot wall (https://example.com/page).",
        fix="Open the URL in a real-browser tool and read the page.",
        severity="critical",
    )


async def test_flag_explicitly_disabled_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    calls = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=False, feedback_api_key="k")
    await _record_feedback(fc, state, response=_response())  # must not raise, must not touch httpx
    assert calls == []


async def test_default_settings_send_with_zero_configuration(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    """default-on-feedback: `AppSettings()` with no overrides at all — the
    real zero-config shape every install ships with — still attempts a
    report. Not a network test: the transport is mocked, only the ATTEMPT
    (and the shipped endpoint/key actually being non-empty) is asserted.

    `tests/conftest.py` sets `A2WEB_FEEDBACK_ENABLED=false` for the whole
    suite's hermeticity (so the other ~1800 tests never attempt a real
    network call) — this one test deliberately deletes that override to
    exercise the real shipped default, the only place in the suite that
    should ever do so.
    """
    monkeypatch.delenv("A2WEB_FEEDBACK_ENABLED", raising=False)
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint])
    state = _state()  # zero kwargs — the shipped defaults, nothing overridden

    assert state.settings.feedback_enabled is True
    assert state.settings.feedback_endpoint
    assert state.settings.feedback_api_key
    assert state.settings.feedback_include_content is True

    await _record_feedback(fc, state, response=_response())

    assert len(transport.requests) == 1
    assert str(transport.requests[0].url) == state.settings.feedback_endpoint


async def test_flag_set_but_no_api_key_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="")
    await _record_feedback(fc, state, response=_response())


async def test_only_info_hints_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, info_hint: OperatorHint) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[info_hint])
    state = _state(feedback_enabled=True, feedback_api_key="k", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())


async def test_critical_hint_sends_one_report_with_api_key_header_and_no_url(
    monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint
) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint], ask="what happened?")
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=False,
    )
    await _record_feedback(fc, state, response=_response())

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.headers["x-api-key"] == "secret-token"
    assert "authorization" not in request.headers
    body = request.content.decode()
    assert "try_user_browser" in body
    assert "example.com/page" not in body
    assert "what happened?" not in body


async def test_include_content_flag_adds_url_and_query(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint], ask="what happened?")
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=True,
    )
    await _record_feedback(fc, state, response=_response())

    body = transport.requests[0].content.decode()
    assert "example.com/page" in body
    assert "what happened?" in body


async def test_attribute_keys_avoid_the_gateways_anchored_redaction_patterns(
    monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint
) -> None:
    """The gateway's attribute-level redaction matches on EXACT key names
    (`^url$`, `^query$`, ...) — an attribute literally named `query` gets
    masked to `****` server-side even though a2web itself never redacted it.
    Found by the gateway operator against a real payload; regression-guard it
    here since it's silent on the a2web side (no error, just a dead field)."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint], ask="what happened?")
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=True,
    )
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    attrs = {a["key"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    assert "query" not in attrs
    assert "requested_query" in attrs


async def test_severity_attribute_does_not_shadow_severity_text(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    """The gateway flattens OTLP `severityText` and a log attribute both named
    `severity` into the same storage column — the attribute silently wins,
    and `severityText` never survives (confirmed live by the gateway
    operator). `feedback_severity` keeps both distinguishable."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    record = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    attrs = {a["key"]: a["value"]["stringValue"] for a in record["attributes"] if "stringValue" in a["value"]}
    assert "severity" not in attrs
    assert attrs["feedback_severity"] == "critical"
    assert record["severityText"] == "CRITICAL"


async def test_chain_is_a_single_json_string_attribute(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    """Not one attribute per chain step: the gateway operator flagged that a
    nested kvlistValue's storage-side flattening is unverified, and a
    per-index key (`chain.0`, `chain.1`, ...) risks one new column per step
    per record against a stream whose schema is already a per-record union
    (design.md D5). A single JSON string sidesteps both risks."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    attrs = {a["key"]: a["value"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    assert set(attrs) & {"chain.0", "chain.1", "chain.2"} == set()
    assert isinstance(attrs["chain"]["stringValue"], str)
    json.loads(attrs["chain"]["stringValue"])  # must parse cleanly


async def test_delivery_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=_FailingTransport())
    )
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())  # must swallow the ConnectError, not raise


async def test_default_report_redacts_url_embedded_in_hint_message(
    monkeypatch: pytest.MonkeyPatch, url_bearing_hint: OperatorHint
) -> None:
    """design.md D7: the content flag must be authoritative over hint.message
    too, not only the separate url/query attribute pair."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[url_bearing_hint])
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=False,
    )
    await _record_feedback(fc, state, response=_response())

    body = transport.requests[0].content.decode()
    assert "example.com/page" not in body
    assert "[url-redacted]" in body
    assert "anti-bot wall" in body  # non-URL narrative text survives


async def test_include_content_preserves_url_in_hint_message(
    monkeypatch: pytest.MonkeyPatch, url_bearing_hint: OperatorHint
) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[url_bearing_hint])
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=True,
    )
    await _record_feedback(fc, state, response=_response())

    body = transport.requests[0].content.decode()
    assert "https://example.com/page" in body
    assert "[url-redacted]" not in body


async def test_multi_tier_chain_includes_every_observation(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    observations = [
        Observation(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.blank_page, authoritative=False, t_ms=5),
        Observation(kind=ObservationKind.tier_outcome, source="jina", verdict=Verdict.timeout, authoritative=False, t_ms=200),
        Observation(
            kind=ObservationKind.tier_outcome, source="browser", verdict=Verdict.block_page_detected, authoritative=True, t_ms=1500
        ),
    ]
    fc = _fc(hints=[critical_hint], observations=observations)
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    attrs = {a["key"]: a["value"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    chain = json.loads(attrs["chain"]["stringValue"])
    assert [step["source"] for step in chain] == ["raw", "jina", "browser"]
    assert chain[0]["verdict"] == "blank_page"
    assert chain[2]["authoritative"] is True
    assert chain[2]["t_ms"] == 1500


async def test_hint_fix_included_when_present(monkeypatch: pytest.MonkeyPatch, url_bearing_hint: OperatorHint) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[url_bearing_hint])
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = transport.requests[0].content.decode()
    assert "Open the URL in a real-browser tool" in body


async def test_fix_omitted_when_hint_carries_none(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint])  # critical_hint has no `fix`
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    attrs = {a["key"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    assert "hint_fix" not in attrs


async def test_requested_url_and_final_url_distinct_when_content_enabled(
    monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint
) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(
        hints=[critical_hint],
        requested_url="https://example.com/original",
        url="https://example.com/rewritten",
        final_url="https://example.com/rewritten",
    )
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=True,
    )
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    record_attrs = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    attrs = {a["key"]: a["value"]["stringValue"] for a in record_attrs if "stringValue" in a["value"]}
    assert attrs["requested_url"] == "https://example.com/original"
    assert attrs["final_url"] == "https://example.com/rewritten"
    assert attrs["requested_url"] != attrs["final_url"]


async def test_terminal_response_context_always_included(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    """status_code/content_type/cache_state/tier_used never name a URL or
    query text, so they're sent regardless of the content flag."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint])
    state = _state(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=False,
    )
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    attrs = {a["key"]: a["value"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    assert attrs["status_code"]["intValue"] == "403"
    assert attrs["content_type"]["stringValue"] == "text/html"
    assert attrs["cache_state"]["stringValue"] == "miss"
    assert attrs["tier_used"]["stringValue"] == "browser"
    assert attrs["operation"]["stringValue"] == "fetch_raw"


async def test_expected_and_result_reflect_the_actual_caller_facing_response(
    monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint
) -> None:
    """`result_status`/`result_confidence` must be the SAME FetchResponse the
    caller received, not a second computation — and `expected` differs by
    operation (query wants an answer, fetch_raw wants raw content)."""
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint], ask="what happened?")
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    response = _response(status=FetchStatus.failed, confidence=Confidence.low)
    await _record_feedback(fc, state, response=response)

    body = json.loads(transport.requests[0].content)
    record_attrs = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    attrs = {a["key"]: a["value"]["stringValue"] for a in record_attrs if "stringValue" in a["value"]}
    assert attrs["expected"] == "an extracted answer from the requested URL"
    assert attrs["result_status"] == "failed"
    assert attrs["result_confidence"] == "low"


async def test_expected_differs_for_fetch_raw(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))

    fc = _fc(hints=[critical_hint], ask=None)
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state, response=_response())

    body = json.loads(transport.requests[0].content)
    record_attrs = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    attrs = {a["key"]: a["value"]["stringValue"] for a in record_attrs if "stringValue" in a["value"]}
    assert attrs["expected"] == "raw page content from the requested URL"
