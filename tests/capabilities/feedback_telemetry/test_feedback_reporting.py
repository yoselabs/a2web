"""Opt-in failure-feedback reporting (openspec `add-a2web-feedback-channel`).

Offline unit tests directly against `_record_feedback` — no App, no real fetch,
no network. `AppState.breakers`/`proxy_pool`/`sqlite` are not read by the
function under test, so `None` stand-ins are enough (this module is not
type-checked by `make ty`, which scopes to `src/` only).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from a2web.decision_log import Observation, ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.pipeline import _record_feedback
from a2web.hints import OperatorHint
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState

_RealAsyncClient = httpx.AsyncClient


def _fc(*, hints: list[OperatorHint], ask: str | None = None) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=time.perf_counter(),
            profile_hash="test",
            bypass_cache=True,
            ask=ask,
        ),
        resources=FetchResources(sqlite=None),
        url="https://example.com/page",
        final_url="https://example.com/page",
    )
    fc.operator_hints.extend(hints)
    fc.observations.append(
        Observation(kind=ObservationKind.tier_outcome, source="browser", verdict=Verdict.block_page_detected, authoritative=True, t_ms=10)
    )
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


async def test_flag_unset_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    calls = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=False, feedback_api_key="k")
    await _record_feedback(fc, state)  # must not raise, must not touch httpx
    assert calls == []


async def test_flag_set_but_no_api_key_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="")
    await _record_feedback(fc, state)


async def test_only_info_hints_makes_no_http_call(monkeypatch: pytest.MonkeyPatch, info_hint: OperatorHint) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    fc = _fc(hints=[info_hint])
    state = _state(feedback_enabled=True, feedback_api_key="k", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state)


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
    await _record_feedback(fc, state)

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
    await _record_feedback(fc, state)

    body = transport.requests[0].content.decode()
    assert "example.com/page" in body
    assert "what happened?" in body


async def test_delivery_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch, critical_hint: OperatorHint) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=_FailingTransport())
    )
    fc = _fc(hints=[critical_hint])
    state = _state(feedback_enabled=True, feedback_api_key="secret-token", feedback_endpoint="https://gateway.test/v1/logs")
    await _record_feedback(fc, state)  # must swallow the ConnectError, not raise
