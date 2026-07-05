"""OpenAI-compatible provider — any `chat/completions` endpoint.

Satisfies the text-in/text-out Provider Protocol against any OpenAI-compatible
backend (OpenAI itself, Gemini's OpenAI-compatible endpoint, local runtimes
like Ollama/LiteLLM, or an operator-run gateway) via the `openai` SDK pointed
at a configured `base_url`. No JSON-mode / tool-use / streaming — the extractor
prompts for JSON in text and the wobble funnel parses it, identical to the
Anthropic path.

Construction reads the standard OpenAI SDK env vars via the manifest: an API key
(default `OPENAI_API_KEY`; missing → LLMNotAvailable → `Unavailable`) and an
optional `base_url` (empty → OpenAI proper). The resolved model rides on
`default_model` (the manifest picks it from `OPENAI_MODEL` or a host
recommendation). This backend derives as the LAST-resort fallback in the auto
order, gated on the key's presence — so it never shadows a working Claude or
Anthropic path and needs no explicit pin.

Cost note: pricing for arbitrary endpoints is unknown, so `cost_usd` is always
`0.0` (the documented "could not price" sentinel) — never a fabricated figure.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..errors import LLMNotAvailable
from .base import ProviderResponse

if TYPE_CHECKING:
    from ..prompts import PromptParts


class OpenAICompatibleProvider:
    """Provider implementation using the `openai` SDK against a `base_url`.

    Construction reads the endpoint from `base_url` and the API key from
    `os.environ` via the configured env var (default `A2WEB_LLM_API_KEY`).
    Missing endpoint or key → LLMNotAvailable.
    """

    name: str = "openai_compatible"

    def __init__(self, *, base_url: str = "", api_key_env: str = "OPENAI_API_KEY", default_model: str = "") -> None:
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise LLMNotAvailable(f"No OpenAI-compatible API key found. Set the {api_key_env} environment variable.")

        # `default_model` is the model resolved by the manifest (OPENAI_MODEL →
        # host recommendation). The extraction resource reads it so the model
        # travels with the provider rather than the Anthropic-shaped `llm_model`.
        self.default_model = default_model

        from openai import AsyncOpenAI

        # Empty base_url → let the SDK target OpenAI proper (its own default).
        endpoint = (base_url or "").strip()
        self._client = AsyncOpenAI(api_key=api_key, base_url=endpoint) if endpoint else AsyncOpenAI(api_key=api_key)

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
        from openai import APIError

        # `parts` (cache-aware prompt split) has no OpenAI breakpoint API — fall
        # back to byte-equivalent concatenation per the Provider protocol's
        # markerless-backend rule. Otherwise use the flat system/user path.
        if parts is not None and parts.cache_prefix != "":
            system_str = parts.system
            user_text = parts.cache_prefix + parts.tail
        else:
            system_str = "\n\n".join(system) if isinstance(system, tuple) else system
            user_text = user

        messages: list[dict[str, str]] = []
        if system_str:
            messages.append({"role": "system", "content": system_str})
        messages.append({"role": "user", "content": user_text})

        # Build the request as a splatted dict (mirrors AnthropicProvider) so the
        # SDK's heavily-overloaded `create` typing does not fight the plain
        # message dicts. `max_tokens` is the broadly-supported cap across
        # OpenAI-compatible endpoints (Gemini-compat, LiteLLM, Ollama, older
        # OpenAI); some newer OpenAI models require `max_completion_tokens`
        # instead — a per-backend wrinkle the bench spike surfaces before freeze.
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        t0 = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except APIError as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return ProviderResponse(
                text="",
                model=model,
                latency_ms=latency_ms,
                raw={"error": str(exc), "status": getattr(exc, "status_code", None)},
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = ""
        if response.choices:
            text = response.choices[0].message.content or ""

        usage = response.usage
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0

        return ProviderResponse(
            text=text,
            model=getattr(response, "model", model) or model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=0.0,  # unknown pricing for arbitrary endpoints — never guessed
            latency_ms=latency_ms,
        )


__all__ = ["OpenAICompatibleProvider"]
