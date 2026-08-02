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


# --------------------------------------------------------------------- #
# The typed branch — `guard_tool`'s `except AppError`
# --------------------------------------------------------------------- #
#
# Until 2026-07-31 a2web raised none of a2effect's five types, so that branch
# was unreachable: EVERY failure quarantined into `UnexpectedDefect` kind
# `"bug"` and opened with "Internal error". An operator whose ANTHROPIC_API_KEY
# was simply unset was told a2web had a bug — so the actionable failure and the
# null-deref reached the caller identically, and four of the five
# `_KIND_LABELS` entries could never be produced by anything.
#
# The retype landed; nothing pinned it. These do. They matter more than they
# look: the branch is reachable only while some a2web code path raises an
# `AppError` subclass, and that is one `raise ValueError` refactor away from
# silently reverting to the old behaviour with no test failing.


@pytest.mark.asyncio
async def test_a_missing_llm_credential_is_an_auth_error_not_a_bug(monkeypatch: pytest.MonkeyPatch) -> None:
    """The §8 product defect: an unset key must not render as an internal bug."""
    from a2web.packages.llm_extract import LLMNotAvailable

    reason = "no ANTHROPIC_API_KEY and no Claude Code session"

    async def _no_llm(*_args: object, **_kwargs: object) -> object:
        raise LLMNotAvailable(reason)

    monkeypatch.setattr("a2web.routers.orchestrate", _no_llm)

    async with mcp_client() as client:
        result = await client.call_tool("query", {"url": "https://example.com", "query": "anything"}, raise_on_error=False)

    prose = result.content[0].text
    assert "Authentication required (LLMNotAvailable)" in prose, f"the typed branch did not fire; got {prose!r}"
    assert reason in prose, "the actionable reason must survive to the caller"
    assert "Internal error" not in prose, "a missing credential rendered as an internal bug — the §8 defect"
    assert "UnexpectedDefect" not in prose, "the error was quarantined instead of recognised"

    # A directly-raised `AppError` carries no wrapped `cause` — it IS the error,
    # so `type`/`kind` sit at the envelope's top level. (The quarantined path
    # above is the one with a `cause`, because there the real exception is
    # wrapped inside an `UnexpectedDefect`.)
    envelope = result.structured_content
    assert envelope is not None, "structured_content is null — the error envelope was destroyed"
    error = envelope["error"]
    assert error["type"] == "LLMNotAvailable"
    assert error["kind"] == "auth", f"a missing credential must classify as auth, got {error['kind']!r}"
    assert error["retryable"] is False, "retrying a missing key never helps, and a machine caller acts on this"


@pytest.mark.asyncio
async def test_an_absent_resource_is_infra_not_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ResourceUnavailable` is INFRA, and the distinction is deliberate.

    Nothing is wrong with a credential — a declared dependency is simply
    absent. Rendering it as "Authentication required" would send an operator to
    check keys that are fine. This asserts the two typed failures stay
    distinguishable, which is the entire value of a taxonomy over one label.
    """
    from a2web.state import ResourceUnavailable

    async def _absent(*_args: object, **_kwargs: object) -> object:
        raise ResourceUnavailable("browser backend was not provisioned")

    monkeypatch.setattr("a2web.routers.orchestrate", _absent)

    async with mcp_client() as client:
        result = await client.call_tool("query", {"url": "https://example.com", "query": "anything"}, raise_on_error=False)

    prose = result.content[0].text
    assert "Service unavailable (ResourceUnavailable)" in prose, f"expected the infra label; got {prose!r}"
    assert "Authentication required" not in prose, "an absent resource must not be reported as a credential problem"

    error = (result.structured_content or {})["error"]
    assert error["kind"] == "infra", f"an absent dependency must classify as infra, got {error['kind']!r}"
    assert error["retryable"] is True, "infra is defined as retryable — the opposite of the auth case above"


@pytest.mark.asyncio
async def test_an_untyped_fault_still_quarantines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-vacuity for the two above: the `bug` label must still be produced.

    If `format_error_prose` degraded to labelling everything by its class name,
    both tests above would pass and the taxonomy would be gone. This pins the
    other side — an exception that is NOT an `AppError` is still quarantined.
    """

    async def _untyped(*_args: object, **_kwargs: object) -> object:
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr("a2web.routers.orchestrate", _untyped)

    async with mcp_client() as client:
        result = await client.call_tool("query", {"url": "https://example.com", "query": "anything"}, raise_on_error=False)

    prose = result.content[0].text
    assert "Internal error (UnexpectedDefect)" in prose, f"an untyped fault must still quarantine; got {prose!r}"
