"""`report_feedback` (openspec `adopt-shelf-mcp-feedback`).

The tool's own schema/transport/gating are the shelf `mcp-feedback`
package's concern, tested there. These tests cover a2web's own
integration surface: config passthrough (`feedback_enabled`/`endpoint`/
`api_key`), `extra_instructions` wiring, and that the mounted tool is
reachable through the real MCP server with a `subject` parameter (not
`url`).
"""

from __future__ import annotations

import json

import httpx
import pytest

from a2web.settings import AppSettings
from tests._helpers.mcp import mcp_client

_RealAsyncClient = httpx.AsyncClient


class _RecordingTransport(httpx.MockTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return response

        super().__init__(handler)


class _FailingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")


async def test_flag_off_sends_nothing_and_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    settings = AppSettings(feedback_enabled=False)

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool("report_feedback", {"subject": "https://example.com/page", "note": "wrong answer"})

    assert result.structured_content["sent"] is False


async def test_endpoint_and_key_configured_but_flag_off_still_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """design D4: `feedback_enabled` is a2web's own master switch — endpoint/key
    being configured is not enough on its own, matching the mechanical
    reporter's own gating semantics before this adoption."""
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: (_ for _ in ()).throw(AssertionError("no client should be built")))
    settings = AppSettings(feedback_enabled=False, feedback_endpoint="https://gateway.test/v1/logs", feedback_api_key="k")

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool("report_feedback", {"subject": "s", "note": "n"})

    assert result.structured_content["sent"] is False


async def test_flag_on_sends_subject_note_wanted_regardless_of_include_content(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))
    settings = AppSettings(
        feedback_enabled=True,
        feedback_api_key="secret-token",
        feedback_endpoint="https://gateway.test/v1/logs",
        feedback_include_content=False,  # deliberately off — must not gate report_feedback
    )

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool(
            "report_feedback",
            {"subject": "https://example.com/product/123", "note": "wrong item entirely", "wanted": "the RTX 4090 listing"},
        )

    assert result.structured_content["sent"] is True
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.headers["x-api-key"] == "secret-token"
    body = json.loads(request.content)
    record = body["resourceLogs"][0]["scopeLogs"][0]
    attrs = {a["key"]: a["value"]["stringValue"] for a in record["logRecords"][0]["attributes"]}
    assert attrs["subject"] == "https://example.com/product/123"
    assert attrs["note"] == "wrong item entirely"
    assert attrs["wanted"] == "the RTX 4090 listing"


async def test_extra_instructions_names_subject_as_the_fetched_url(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings(feedback_enabled=False)

    async with mcp_client(settings=settings) as client:
        tools = await client.list_tools()

    report = next(t for t in tools if t.name == "report_feedback")
    assert "subject = the URL you fetched." in report.description
    assert set(report.inputSchema["properties"]) == {"subject", "note", "request", "response", "wanted"}
    assert "url" not in report.inputSchema["properties"]


async def test_default_settings_send_with_zero_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """default-on-feedback: `AppSettings()` with no overrides — the real
    zero-config shape every install ships with — still attempts a report
    when the agent calls report_feedback.

    `tests/conftest.py` sets `A2WEB_FEEDBACK_ENABLED=false` for the whole
    suite's hermeticity — this one test deliberately deletes that override
    to exercise the real shipped default.
    """
    monkeypatch.delenv("A2WEB_FEEDBACK_ENABLED", raising=False)
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))
    settings = AppSettings()  # zero kwargs — the shipped defaults

    assert settings.feedback_enabled is True
    assert settings.feedback_endpoint
    assert settings.feedback_api_key

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool("report_feedback", {"subject": "s", "note": "n"})

    assert result.structured_content["sent"] is True
    assert len(transport.requests) == 1
    assert str(transport.requests[0].url) == settings.feedback_endpoint


async def test_disclosure_sentence_on_query_fetch_raw_and_report_feedback_not_cookies_refresh() -> None:
    """default-on-feedback: the disclosure lives in tools/list (universal,
    unlike resources/list) — query and fetch_raw carry it because the
    MECHANICAL reporter can fire from either without report_feedback ever
    being called; cookies_refresh never triggers it, so it stays silent."""
    settings = AppSettings(feedback_enabled=False)

    async with mcp_client(settings=settings) as client:
        tools = await client.list_tools()

    by_name = {t.name: t for t in tools}
    disclosure = "a2web reports its own failures to its maintainers by default"
    assert disclosure in by_name["query"].description
    assert disclosure in by_name["fetch_raw"].description
    assert disclosure in by_name["report_feedback"].description
    assert "A2WEB_FEEDBACK_ENABLED=false" in by_name["query"].description
    if "cookies_refresh" in by_name:
        assert disclosure not in by_name["cookies_refresh"].description


async def test_request_and_response_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _RecordingTransport(httpx.Response(200, json={"partialSuccess": {}}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=transport))
    settings = AppSettings(feedback_enabled=True, feedback_api_key="k", feedback_endpoint="https://gateway.test/v1/logs")

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool(
            "report_feedback",
            {
                "subject": "https://example.com/product/123",
                "note": "wrong item entirely",
                "request": "query(url=..., query='RTX 4090 price')",
                "response": "a used-parts listing, not a GPU",
            },
        )

    assert result.structured_content["sent"] is True
    body = json.loads(transport.requests[0].content)
    attrs = {a["key"]: a["value"]["stringValue"] for a in body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]}
    assert attrs["request"] == "query(url=..., query='RTX 4090 price')"
    assert attrs["response"] == "a used-parts listing, not a GPU"


async def test_delivery_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=_FailingTransport()))
    settings = AppSettings(feedback_enabled=True, feedback_api_key="k", feedback_endpoint="https://gateway.test/v1/logs")

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool("report_feedback", {"subject": "https://example.com/x", "note": "note"})

    assert result.structured_content["sent"] is True  # attempted — delivery failure is swallowed
