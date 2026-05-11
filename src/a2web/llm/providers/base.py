"""Provider Protocol — what every LLM backend implements.

The contract is intentionally tight: text-in, text-out, with token + cost +
latency accounting on the response. Multi-modal, streaming, and tool-use
features stay out of scope — the Extractor's job is to turn a (content,
question) pair into an answer string, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ProviderResponse:
    """One completion result. Token counts and cost are best-effort.

    `cost_usd == 0.0` means the provider could not compute a price (e.g. on
    cache hits or for providers without a hardcoded pricing table). Callers
    that care about audit-grade cost should not treat 0.0 as "free."

    `raw` carries provider-specific debug data — never depend on its shape
    from outside the provider.
    """

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict[str, Any] | None = None


@runtime_checkable
class Provider(Protocol):
    """A completion backend. Implementations live under `providers/`."""

    name: str  # "anthropic", "openrouter", ...

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
        """Submit one user message + (possibly empty) system content.

        `system=()` or `system=""` produces a request with no system content
        — required for faithful WebFetchBaseline reproduction per
        research/123 (Claude Code sends `iK([])` = `[]`).

        `thinking_disabled=True` SHALL disable extended thinking on
        providers that support it. The Extractor always sets this true; the
        eval matrix may flip it for "with thinking" baseline comparisons.

        Implementations MUST NOT raise on routine API errors (rate limits,
        transient network errors) — translate to a `ProviderResponse` with
        empty `text` and a populated `raw["error"]`. Programmer-error
        exceptions (bad config, missing dep) propagate as-is.
        """
        ...
