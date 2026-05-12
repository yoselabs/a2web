"""ClaudeCodeProvider tests.

The provider piggybacks on the user's Claude Code OS session via
`claude-agent-sdk`. We don't actually invoke the real CLI in tests —
we monkey-patch `claude_agent_sdk.query` with an async generator that
yields canned messages.
"""

from __future__ import annotations

from typing import Any

import pytest

from a2web.packages.llm_extract import LLMNotAvailable
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider


@pytest.mark.asyncio
async def test_complete_collects_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: AssistantMessage TextBlocks concatenate, ResultMessage
    supplies cost + token counts."""
    import claude_agent_sdk

    async def fake_query(*, prompt: str, options: Any, transport: Any = None):
        assert "hello content" in prompt or "ask" in prompt
        assert options.tools == []
        assert options.max_turns == 1
        yield claude_agent_sdk.AssistantMessage(
            content=[
                claude_agent_sdk.TextBlock(text="part one. "),
                claude_agent_sdk.TextBlock(text="part two."),
            ],
            model="claude-haiku-4-5-20251001",
            parent_tool_use_id=None,
            error=None,
            usage=None,
            message_id=None,
            stop_reason=None,
            session_id=None,
            uuid=None,
        )
        yield claude_agent_sdk.ResultMessage(
            subtype="success",
            duration_ms=120,
            duration_api_ms=100,
            is_error=False,
            num_turns=1,
            session_id="sess-123",
            stop_reason="end_turn",
            total_cost_usd=0.0012,
            usage={"input_tokens": 80, "output_tokens": 10},
            result="part one. part two.",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            deferred_tool_use=None,
            errors=None,
            api_error_status=None,
            uuid=None,
        )

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    # The provider re-imports query from inside complete(), so patch both
    # the package attribute and the symbol the provider sees.
    import a2web.packages.llm_extract.providers.claude_code as cc_mod

    provider = cc_mod.ClaudeCodeProvider()
    resp = await provider.complete(
        system="be terse",
        user="hello content. ask: what is X?",
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
    )

    assert resp.text == "part one. part two."
    assert resp.model == "claude-haiku-4-5-20251001"
    assert resp.prompt_tokens == 80
    assert resp.completion_tokens == 10
    assert resp.cost_usd == pytest.approx(0.0012)
    assert resp.latency_ms >= 0


@pytest.mark.asyncio
async def test_complete_handles_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Result-only stream (no AssistantMessage) → empty text, no crash."""
    import claude_agent_sdk

    async def fake_query(*, prompt: str, options: Any, transport: Any = None):
        yield claude_agent_sdk.ResultMessage(
            subtype="success",
            duration_ms=50,
            duration_api_ms=40,
            is_error=False,
            num_turns=1,
            session_id="s",
            stop_reason="end_turn",
            total_cost_usd=0.0,
            usage={"input_tokens": 5, "output_tokens": 0},
            result=None,
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            deferred_tool_use=None,
            errors=None,
            api_error_status=None,
            uuid=None,
        )

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    provider = ClaudeCodeProvider()
    resp = await provider.complete(
        system="",
        user="anything",
        model="claude-haiku-4-5-20251001",
    )
    assert resp.text == ""
    assert resp.prompt_tokens == 5
    assert resp.completion_tokens == 0


@pytest.mark.asyncio
async def test_complete_translates_cli_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing `claude` CLI → LLMNotAvailable, not a generic crash."""
    import claude_agent_sdk

    async def fake_query(*, prompt: str, options: Any, transport: Any = None):
        raise claude_agent_sdk.CLINotFoundError("claude not on PATH")
        yield  # pragma: no cover — generator must be a generator

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    provider = ClaudeCodeProvider()
    with pytest.raises(LLMNotAvailable, match="Claude Code CLI is unavailable"):
        await provider.complete(
            system="",
            user="x",
            model="claude-haiku-4-5-20251001",
        )


@pytest.mark.asyncio
async def test_complete_catches_generic_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-CLI errors → empty response with raw['error'] populated."""
    import claude_agent_sdk

    async def fake_query(*, prompt: str, options: Any, transport: Any = None):
        raise RuntimeError("rate limit eg")
        yield  # pragma: no cover

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    provider = ClaudeCodeProvider()
    resp = await provider.complete(
        system="",
        user="x",
        model="claude-haiku-4-5-20251001",
    )
    assert resp.text == ""
    assert resp.raw is not None
    assert "rate limit eg" in resp.raw["error"]
