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
from typing import TYPE_CHECKING, Any

from ..errors import LLMNotAvailable
from .base import ProviderResponse, extract_token_counts

if TYPE_CHECKING:
    from ..prompts import PromptParts


class ClaudeCodeProvider:
    """Provider that runs prompts through the user's Claude Code OS session.

    No API key is required: the underlying `claude` CLI handles auth (OAuth
    subscription, API key, or whichever Claude Code is configured to use).
    Missing `claude-agent-sdk` or missing `claude` CLI → `LLMNotAvailable`
    with an actionable hint.
    """

    name: str = "claude-code"

    def __init__(self) -> None:
        # a2web v0.7+: `claude-agent-sdk` is a baseline dep, no ImportError gate.
        # OAuth/session detection happens at first `complete()` call.
        return

    async def complete(
        self,
        *,
        system: tuple[str, ...] | str,
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thinking_disabled: bool = True,
        parts: PromptParts | None = None,
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

        # v0.19: `claude-agent-sdk` exposes no `cache_control` API (probed
        # 2026-05-23 against SDK ≥0.1.80 — zero references in source). The
        # CLI binary applies caching internally given a byte-stable prefix.
        # When `parts` is provided we unpack to (system, prefix+tail) and
        # rely on `EXTRACT_CACHEABLE_V1` keeping the prefix stable across
        # different `ask` values.
        if parts is not None and parts.cache_prefix != "":
            system_str = parts.system
            prompt_str = parts.cache_prefix + parts.tail
        else:
            prompt_str = user
            if isinstance(system, tuple):
                system_str = "\n\n".join(system) if system else ""
            else:
                system_str = system

        # NOTE: claude-agent-sdk treats `system_prompt=None` as "load the
        # claude_code preset" (~23k extra prompt tokens per call — verified
        # via probe_sdk.py, 2026-05-19). Pass an explicit string (even "")
        # to opt out of the preset and drop ~12k tokens / ~43% per fetch.
        #
        # v0.20 (2026-05-24): three further opt-outs strip another ~22-27k
        # tokens per call (CLAUDE.md auto-discovery, skill registry, slash
        # command pre-registration). Eval at
        # `eval/findings_2026-05-24-claude-code-cli-flag-sweep.md` — net
        # session cost ~41% lower. `--bare` would do more but kills OAuth, so we
        # use the narrow opt-outs that keep keychain-based auth working.
        options_kwargs: dict[str, Any] = {
            "model": model,
            "tools": [],  # pure completion — no tool use
            "max_turns": 1,
            "max_thinking_tokens": 0 if thinking_disabled else None,
            "system_prompt": system_str,  # always — None silently activates claude_code preset
            "setting_sources": [],  # skip user/project/local CLAUDE.md discovery
            "skills": [],  # don't load skill registry
            "extra_args": {"disable-slash-commands": None},
        }
        if thinking_disabled:
            options_kwargs["thinking"] = ThinkingConfigDisabled(type="disabled")

        options = ClaudeAgentOptions(**{k: v for k, v in options_kwargs.items() if v is not None})

        text_parts: list[str] = []
        result_msg: ResultMessage | None = None
        resolved_model = model

        t0 = time.perf_counter()
        try:
            async for msg in query(prompt=prompt_str, options=options):
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
            prompt_tokens, completion_tokens, _, _ = extract_token_counts(result_msg.usage or {})
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
                    "usage": result_msg.usage,
                }
                if result_msg
                else None
            ),
        )


__all__ = ["ClaudeCodeProvider"]
