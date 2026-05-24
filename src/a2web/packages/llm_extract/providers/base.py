"""Provider Protocol — what every LLM backend implements.

The contract is intentionally tight: text-in, text-out, with token + cost +
latency accounting on the response. Multi-modal, streaming, and tool-use
features stay out of scope — the Extractor's job is to turn a (content,
question) pair into an answer string, nothing more.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..prompts import PromptParts


def extract_token_counts(usage: Mapping[str, Any] | Any) -> tuple[int, int, int, int]:
    """Pull (prompt_total, output, cache_creation, cache_read) from an Anthropic usage object.

    Anthropic's usage shape (both raw API and claude-agent-sdk) splits the
    prompt across three counters: fresh ``input_tokens`` plus
    ``cache_creation_input_tokens`` (writes) and ``cache_read_input_tokens``
    (reads). Reporting only ``input_tokens`` understates the prompt by
    100-1000x on warm sessions where the bulk of the prompt is served from
    cache. Returns the summed ``prompt_total`` plus the individual
    breakdown so callers can compute accurate ``cost_usd`` using cache-tier
    pricing. Accepts a dict (claude-agent-sdk) or an attribute-style
    object (anthropic.types.Usage) transparently.
    """

    def _read(key: str) -> int:
        if isinstance(usage, Mapping):
            return int(usage.get(key) or 0)
        return int(getattr(usage, key, 0) or 0)

    fresh = _read("input_tokens")
    cache_creation = _read("cache_creation_input_tokens")
    cache_read = _read("cache_read_input_tokens")
    output = _read("output_tokens")
    prompt_total = fresh + cache_creation + cache_read
    return prompt_total, output, cache_creation, cache_read


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

    name: str  # "anthropic", "claude_code"

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
        """Submit one user message + (possibly empty) system content.

        `system=()` or `system=""` produces a request with no system content
        — required for faithful WebFetchBaseline reproduction per
        research/123 (Claude Code sends `iK([])` = `[]`).

        `thinking_disabled=True` SHALL disable extended thinking on
        providers that support it. The Extractor always sets this true; the
        eval matrix may flip it for "with thinking" baseline comparisons.

        `parts` (v0.19): when provided AND `parts.cache_prefix != ""`,
        providers SHOULD place a cache breakpoint between `parts.cache_prefix`
        and `parts.tail`. Providers without a marker API (claude-agent-sdk)
        SHALL fall back to byte-equivalent concatenation. When `parts` is
        `None` or its `cache_prefix` is empty, providers SHALL use the
        legacy flat-string path.

        Implementations MUST NOT raise on routine API errors (rate limits,
        transient network errors) — translate to a `ProviderResponse` with
        empty `text` and a populated `raw["error"]`. Programmer-error
        exceptions (bad config, missing dep) propagate as-is.
        """
        ...
