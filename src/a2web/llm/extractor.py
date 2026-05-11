"""Extractor — runs an LLM over (content, ask) to produce an answer string.

This is the server-side extraction trick that Claude Code's WebFetch uses
internally: the calling agent never sees the page, only the answer. See
`prompts.WEBFETCH_DEFAULT_V1` for the byte-identical template.

Tied to a `Provider` + `PromptTemplate` at construction time. The cache
(extraction-answer LRU) lands in a follow-up commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .prompts import WEBFETCH_DEFAULT_V1, PromptTemplate
from .providers.base import Provider


@dataclass(slots=True)
class ModelSpec:
    """Identifies the LLM to call: provider name + model id.

    Equality keys cache lookups in v0.4. Adding a new provider only requires
    matching `provider` here; the actual instance is looked up in a
    registry on the Extractor side.
    """

    provider: str
    model: str

    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(slots=True)
class ExtractionResult:
    """One Extractor.extract() outcome. Cost + tokens reflect the call that
    actually went over the wire; on a cache hit they SHALL be zero with the
    original metrics preserved in `original_cost_usd` etc.
    """

    answer: str
    model: str
    template_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    original_cost_usd: float | None = None
    raw: dict[str, Any] | None = field(default=None)


class Extractor:
    """Compose a Provider + PromptTemplate into a single `.extract()` call.

    Usage:
        ex = Extractor(
            provider=AnthropicProvider(),
            model=ModelSpec("anthropic", "claude-haiku-4-5-20251001"),
            template=WEBFETCH_DEFAULT_V1,
        )
        result = await ex.extract(content="<markdown>", ask="What is X?")
    """

    def __init__(
        self,
        *,
        provider: Provider,
        model: ModelSpec,
        template: PromptTemplate = WEBFETCH_DEFAULT_V1,
        max_content_chars: int = 100_000,
        max_tokens: int = 1024,
    ) -> None:
        self._provider = provider
        self._model = model
        self._template = template
        self._max_content_chars = max_content_chars
        self._max_tokens = max_tokens

    @property
    def model(self) -> ModelSpec:
        return self._model

    @property
    def template(self) -> PromptTemplate:
        return self._template

    async def extract(self, *, content: str, ask: str) -> ExtractionResult:
        """Run the template over (content, ask). Returns ExtractionResult."""
        truncated, was_truncated = _truncate(content, self._max_content_chars)
        user = self._template.user_template.format(content=truncated, ask=ask)

        response = await self._provider.complete(
            system=self._template.system,
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )

        return ExtractionResult(
            answer=response.text,
            model=response.model,
            template_name=self._template.name,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            cache_hit=False,
            raw={"truncated": was_truncated} if was_truncated else None,
        )


def _truncate(content: str, cap: int) -> tuple[str, bool]:
    """Truncate to `cap` chars with a clear marker. Matches WebFetch's
    `BD_ = 100000` constant by default (research/123)."""
    if len(content) <= cap:
        return content, False
    return content[:cap] + f"\n\n[Content truncated to {cap} chars]\n", True


__all__ = ["ExtractionResult", "Extractor", "ModelSpec"]
