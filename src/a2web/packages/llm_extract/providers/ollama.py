"""Ollama provider — local LLM via the Ollama HTTP API.

Ollama exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1`.
We reuse the `openai` SDK pointed at that base URL, same pattern as
OpenRouterProvider. No API key required (anything works — we send "ollama").

Model identifiers match Ollama's tags:
  - "llama3.2:3b"
  - "qwen2.5:7b"
  - "phi3.5:3.8b"
  - "gemma2:2b"

If Ollama isn't running OR the requested model isn't pulled,
`complete()` returns a ProviderResponse with empty text and a populated
`raw["error"]` — same contract as the other providers. Use
`OLLAMA_BASE_URL` env var to point at a remote Ollama instance.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, cast

from ..errors import LLMNotAvailable
from .base import ProviderResponse

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class OllamaProvider:
    """Provider hitting a local (or remote) Ollama server.

    Cost is always 0.0 — local inference is unmetered. Latency is wall
    clock from request to response (mostly GPU/CPU time on your machine,
    so it varies wildly with model size and what else is running).
    """

    name: str = "ollama"

    def __init__(
        self,
        *,
        base_url_env: str = "OLLAMA_BASE_URL",
        default_base_url: str = "http://localhost:11434/v1",
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise LLMNotAvailable("The `openai` SDK is required for OllamaProvider. Run `pip install a2web[llm]`.") from exc

        base_url = os.environ.get(base_url_env, "").strip() or default_base_url

        from openai import AsyncOpenAI

        self._base_url = base_url
        # api_key is required by the SDK but ignored by Ollama.
        self._client = AsyncOpenAI(api_key="ollama", base_url=base_url)

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
        if isinstance(system, tuple):
            system_str = "\n\n".join(system) if system else ""
        else:
            system_str = system

        messages: list[dict[str, Any]] = []
        if system_str:
            messages.append({"role": "system", "content": system_str})
        messages.append({"role": "user", "content": user})

        t0 = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=cast("list[ChatCompletionMessageParam]", messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ProviderResponse(
                text="",
                model=model,
                latency_ms=latency_ms,
                raw={
                    "error": repr(exc),
                    "type": type(exc).__name__,
                    "hint": ("Ollama not running? Try `brew install ollama && ollama serve` and `ollama pull <model>`."),
                },
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content if choice and choice.message else "") or ""
        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        return ProviderResponse(
            text=text,
            model=response.model or model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=0.0,  # local — unmetered
            latency_ms=latency_ms,
            raw={
                "finish_reason": getattr(choice, "finish_reason", None) if choice else None,
                "base_url": self._base_url,
            },
        )


__all__ = ["OllamaProvider"]
