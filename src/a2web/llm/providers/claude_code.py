"""Claude Code provider — piggybacks on the OS session via claude-agent-sdk.

When `ANTHROPIC_API_KEY` is not set but Claude Code is logged in (OAuth
session in `~/.claude`), this provider lets a2web's extractor/judge reach
Haiku/Sonnet without minting a separate API key. The SDK shells out to the
`claude` CLI under the hood and inherits its credentials.

Tools are disabled and `max_turns=1` so the model produces a single text
completion — no file edits, no MCP calls, no tool use. Matches the
Provider Protocol's text-in / text-out contract.

Cost + token accounting come from the SDK's `ResultMessage` directly
(Claude Code already tracks usage centrally), so this provider does NOT
maintain its own pricing table — `cost_usd` is whatever the SDK reports
or 0.0 if the field is absent (subscription / not-billable session).
"""

from __future__ import annotations

import time
from typing import Any

from ..errors import LLMNotAvailable
from .base import ProviderResponse


class ClaudeCodeProvider:
    """Provider that runs prompts through the user's Claude Code OS session.

    No API key is required: the underlying `claude` CLI handles auth (OAuth
    subscription, API key, or whichever Claude Code is configured to use).
    Missing `claude-agent-sdk` or missing `claude` CLI → `LLMNotAvailable`
    with an actionable hint.
    """

    name: str = "claude-code"

    def __init__(self) -> None:
        try:
            import claude_agent_sdk  # noqa: F401 — import-side check
        except ImportError as exc:
            raise LLMNotAvailable(
                "The `claude-agent-sdk` package is not installed. Run "
                "`pip install a2web[llm]` (or add `claude-agent-sdk` to "
                "your environment)."
            ) from exc

    async def complete(
        self,
        *,
        system: tuple[str, ...] | str,
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thinking_disabled: bool = True,
    ) -> ProviderResponse:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            CLIConnectionError,
            CLINotFoundError,
            ResultMessage,
            TextBlock,
            ThinkingConfigDisabled,
            query,
        )

        if isinstance(system, tuple):
            system_str = "\n\n".join(system) if system else ""
        else:
            system_str = system

        options_kwargs: dict[str, Any] = {
            "model": model,
            "tools": [],  # pure completion — no tool use
            "max_turns": 1,
            "max_thinking_tokens": 0 if thinking_disabled else None,
        }
        if system_str:
            options_kwargs["system_prompt"] = system_str
        if thinking_disabled:
            options_kwargs["thinking"] = ThinkingConfigDisabled(type="disabled")

        options = ClaudeAgentOptions(**{k: v for k, v in options_kwargs.items() if v is not None})

        text_parts: list[str] = []
        result_msg: ResultMessage | None = None
        resolved_model = model

        t0 = time.perf_counter()
        try:
            async for msg in query(prompt=user, options=options):
                if isinstance(msg, AssistantMessage):
                    if msg.model:
                        resolved_model = msg.model
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    result_msg = msg
        except (CLINotFoundError, CLIConnectionError) as exc:
            raise LLMNotAvailable(
                f"Claude Code CLI is unavailable: {exc}. Install it from "
                "https://docs.claude.com/en/docs/claude-code/setup or set "
                "ANTHROPIC_API_KEY to use AnthropicProvider instead."
            ) from exc
        except Exception as exc:  # SDK error path → empty response, not crash
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ProviderResponse(
                text="",
                model=resolved_model,
                latency_ms=latency_ms,
                raw={"error": repr(exc)},
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = "".join(text_parts)

        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = 0.0
        if result_msg is not None:
            cost_usd = float(result_msg.total_cost_usd or 0.0)
            usage = result_msg.usage or {}
            prompt_tokens = int(usage.get("input_tokens", 0) or 0)
            completion_tokens = int(usage.get("output_tokens", 0) or 0)
            if max_tokens and completion_tokens > max_tokens:
                # SDK doesn't expose a max_tokens knob; report what actually
                # came back instead of clamping silently.
                pass

        return ProviderResponse(
            text=text,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw=(
                {
                    "is_error": result_msg.is_error,
                    "stop_reason": result_msg.stop_reason,
                    "session_id": result_msg.session_id,
                }
                if result_msg
                else None
            ),
        )


__all__ = ["ClaudeCodeProvider"]
