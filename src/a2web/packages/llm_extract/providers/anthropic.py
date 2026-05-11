"""Anthropic Messages API provider (Haiku, Sonnet, Opus).

Reference implementation of the Provider Protocol for v0.4. Faithful
behavior parity with Claude Code's WebFetch sub-call when paired with
`WEBFETCH_DEFAULT_V1` — empty system, thinking disabled, no tools, single
turn, temperature=0.

The `anthropic` SDK is imported at construction time (or lazily on the
first call) so a bare `from a2web.llm.providers import anthropic` import
without `[llm]` installed does NOT crash; instantiating `AnthropicProvider`
without the SDK raises `LLMNotAvailable` with an actionable hint.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..errors import LLMNotAvailable
from .base import ProviderResponse

# Per-1M-token pricing (USD), Anthropic public list as of 2026-05.
# Used to compute cost_usd. Update when the table moves.
_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
}


def _price_for(model: str) -> tuple[float, float] | None:
    """Return (input_per_M, output_per_M) USD or None if unknown."""
    table = _PRICING.get(model)
    if not table:
        # Match by prefix — model id strings sometimes carry date suffixes.
        for known, prices in _PRICING.items():
            if model.startswith(known):
                return prices["input"], prices["output"]
        return None
    return table["input"], table["output"]


class AnthropicProvider:
    """Provider implementation using the official `anthropic` Python SDK.

    Construction reads the API key from `os.environ` via the configured
    env var (default `ANTHROPIC_API_KEY`). Missing key → LLMNotAvailable.
    Missing `anthropic` SDK (no `[llm]` extra installed) → LLMNotAvailable.
    """

    name: str = "anthropic"

    def __init__(self, *, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        try:
            import anthropic  # noqa: F401  — import-side check only
        except ImportError as exc:
            raise LLMNotAvailable(
                "The `anthropic` SDK is not installed. Run `pip install a2web[llm]` (or add `anthropic` to your environment)."
            ) from exc

        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise LLMNotAvailable(
                f"No Anthropic API key found. Set the {api_key_env} environment "
                "variable to a valid key from https://console.anthropic.com/."
            )

        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)

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
        from anthropic import APIError

        # Normalize system: SDK accepts a string OR an empty omission.
        if isinstance(system, tuple):
            system_str = "\n\n".join(system) if system else ""
        else:
            system_str = system

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": user}],
        }
        if system_str:
            kwargs["system"] = system_str
        if not thinking_disabled:
            # Caller explicitly opted in — leave the SDK default. Anthropic's
            # SDK only emits the thinking field when the user sets it.
            pass

        t0 = time.perf_counter()
        try:
            response = await self._client.messages.create(**kwargs)
        except APIError as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ProviderResponse(
                text="",
                model=model,
                latency_ms=latency_ms,
                raw={"error": str(exc), "status": getattr(exc, "status_code", None)},
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # First text block; multi-block responses concatenated.
        text_parts: list[str] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts)

        usage = response.usage
        prompt_tokens = getattr(usage, "input_tokens", 0)
        completion_tokens = getattr(usage, "output_tokens", 0)

        prices = _price_for(response.model)
        cost_usd = 0.0
        if prices is not None:
            input_price, output_price = prices
            cost_usd = prompt_tokens / 1_000_000 * input_price + completion_tokens / 1_000_000 * output_price

        return ProviderResponse(
            text=text,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )


__all__ = ["AnthropicProvider"]
