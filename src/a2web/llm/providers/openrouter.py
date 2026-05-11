"""OpenRouter provider — multi-model gateway via the OpenAI-compatible API.

OpenRouter proxies dozens of model families (DeepSeek, Qwen, Gemini, Kimi,
GLM, MiniMax, Tencent, …) behind a single OpenAI-shaped endpoint. We use
the official `openai` SDK with `base_url=https://openrouter.ai/api/v1`.

Cost is taken from the response's `usage.cost` field when OpenRouter
provides it (most providers do). When absent, falls back to 0.0 — same
contract as AnthropicProvider on unknown models.

Model strings are passed through verbatim — e.g.
  - "deepseek/deepseek-chat"
  - "qwen/qwen-2.5-72b-instruct"
  - "google/gemini-2.0-flash-001"

Missing key (env `OPENROUTER_API_KEY` by default) → LLMNotAvailable.
Missing `openai` SDK → LLMNotAvailable.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..errors import LLMNotAvailable
from .base import ProviderResponse


class OpenRouterProvider:
    """Provider hitting OpenRouter via the OpenAI-compatible SDK."""

    name: str = "openrouter"

    def __init__(
        self,
        *,
        api_key_env: str = "OPENROUTER_API_KEY",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise LLMNotAvailable(
                "The `openai` SDK is not installed. Run `pip install a2web[llm]`."
            ) from exc

        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise LLMNotAvailable(
                f"No OpenRouter API key found. Set {api_key_env} from "
                "https://openrouter.ai/keys."
            )

        from openai import AsyncOpenAI

        # `default_headers` lets OpenRouter attribute traffic to our app for
        # rate-limit pooling, per their docs.
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/yoselabs/a2web",
                "X-Title": "a2web benchmarks",
            },
        )

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
        # System normalization matches AnthropicProvider's contract.
        if isinstance(system, tuple):
            system_str = "\n\n".join(system) if system else ""
        else:
            system_str = system

        messages: list[dict[str, Any]] = []
        if system_str:
            messages.append({"role": "system", "content": system_str})
        messages.append({"role": "user", "content": user})

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        # Ask OpenRouter to include cost in `usage` (OpenRouter extension).
        extra_body: dict[str, Any] = {"usage": {"include": True}}
        if thinking_disabled:
            # OpenRouter accepts `reasoning: {exclude: true}` for thinking
            # models — silently ignored by non-thinking providers.
            extra_body["reasoning"] = {"exclude": True}
        kwargs["extra_body"] = extra_body

        t0 = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ProviderResponse(
                text="",
                model=model,
                latency_ms=latency_ms,
                raw={"error": repr(exc), "type": type(exc).__name__},
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content if choice and choice.message else "") or ""
        resolved_model = response.model or model

        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost_usd = 0.0
        # OpenRouter exposes `cost` (USD) on usage when usage.include=True.
        cost_attr = getattr(usage, "cost", None)
        if cost_attr is not None:
            try:
                cost_usd = float(cost_attr)
            except (TypeError, ValueError):
                cost_usd = 0.0

        return ProviderResponse(
            text=text,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw={"finish_reason": getattr(choice, "finish_reason", None) if choice else None},
        )


__all__ = ["OpenRouterProvider"]
