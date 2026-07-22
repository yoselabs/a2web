"""The tool-failure path, end-to-end through the real MCP transport.

This path was untested from a2web, and a *total* error-envelope failure
shipped unnoticed because of it: `pyproject.toml` resolved fastmcp 3.2.4,
whose `ToolResult.__init__` accepts only `(content, structured_content,
meta)`, while a2kit's `TypedErrorEnvelopeMiddleware` constructs
`ToolResult(..., is_error=True)`. The keyword was rejected, FastMCP masked
the resulting `TypeError`, and every typed error reached the caller as::

    is_error:           True
    content[0].text:    "ToolResult.__init__() got an unexpected keyword argument 'is_error'"
    structured_content: None

Both channels destroyed, on every host. The real message, the envelope, the
cause chain — all gone, leaving a fault indistinguishable from any other.

That is the ADR-0009 harm class one level down: the invariant says a caller
must never mistake an incomplete retrieval for a complete answer, and the
first thing that requires is that a failure be *legible*. Note the two
mechanisms are distinct and both must work — a walled or empty *retrieval*
is not an exception; it returns successfully carrying `status: failed` +
`retrieval_incomplete: true` + diagnostics + narrative + a critical operator
hint. The error envelope here covers only unanticipated faults.
"""

from __future__ import annotations

import inspect

import pytest
from fastmcp.tools.tool import ToolResult

from tests._helpers.mcp import mcp_client

_REAL_CAUSE = "sqlite connection exploded mid-fetch"


def test_resolved_fastmcp_supports_the_error_flag() -> None:
    """The substrate guard: a resolved combination where the middleware passes
    an argument the constructor rejects is a build failure, not a runtime
    degradation. This asserts the floor holds after any future lock change."""
    params = inspect.signature(ToolResult.__init__).parameters
    assert "is_error" in params, (
        "Resolved FastMCP's ToolResult does not accept `is_error`, which a2kit's "
        "TypedErrorEnvelopeMiddleware passes unconditionally. Every typed error "
        f"will be replaced by a TypeError string. Got params: {list(params)}"
    )


@pytest.mark.asyncio
async def test_tool_fault_surfaces_real_cause_on_both_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool-body exception must reach the caller with its real message on the
    text channel AND a populated envelope on the structured channel."""

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(_REAL_CAUSE)

    monkeypatch.setattr("a2web.routers.orchestrate", _boom)

    async with mcp_client() as client:
        result = await client.call_tool(
            "query",
            {"url": "https://example.com", "query": "anything"},
            raise_on_error=False,
        )

    assert result.is_error is True

    # Text channel: the prose an LLM caller reads.
    prose = result.content[0].text
    assert _REAL_CAUSE in prose, f"real cause missing from the text channel: {prose!r}"

    # Structured channel: the envelope a machine caller parses. `None` here is
    # the exact shape of the shipped defect.
    envelope = result.structured_content
    assert envelope is not None, "structured_content is null — the error envelope was destroyed"
    error = envelope["error"]
    assert error["cause"]["type"] == "RuntimeError"
    assert error["cause"]["message"] == _REAL_CAUSE
