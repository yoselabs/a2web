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
    assert "subject" in report.inputSchema["properties"]
    assert "url" not in report.inputSchema["properties"]


async def test_delivery_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _RealAsyncClient(transport=_FailingTransport()))
    settings = AppSettings(feedback_enabled=True, feedback_api_key="k", feedback_endpoint="https://gateway.test/v1/logs")

    async with mcp_client(settings=settings) as client:
        result = await client.call_tool("report_feedback", {"subject": "https://example.com/x", "note": "note"})

    assert result.structured_content["sent"] is True  # attempted — delivery failure is swallowed
