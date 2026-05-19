"""Extractor — runs an LLM over (content, ask) to produce an answer string.

This is the server-side extraction trick that Claude Code's WebFetch uses
internally: the calling agent never sees the page, only the answer. See
`prompts.WEBFETCH_DEFAULT_V1` for the byte-identical template.

Tied to a `Provider` + `PromptTemplate` at construction time. The cache
(extraction-answer LRU) lands in a follow-up commit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .prompts import WEBFETCH_DEFAULT_V1, PromptTemplate
from .providers.base import Provider

if TYPE_CHECKING:
    from .cache import ExtractionCache


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
class LlmNextLink:
    """Boundary-type for a curated next-link candidate emitted by the LLM.

    The a2web seam converts these into the domain-side `NextLink` pydantic
    model after URL-must-be-in-markdown validation. Lives in the package
    because the package MUST NOT import from `a2web.<domain>`.
    """

    anchor: str
    url: str
    reason: str
    kind: str  # "drilldown" | "related" | "source"


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
    next_links: list[LlmNextLink] = field(default_factory=list)


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
        cache: ExtractionCache | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._template = template
        self._max_content_chars = max_content_chars
        self._max_tokens = max_tokens
        self._cache = cache

    @property
    def model(self) -> ModelSpec:
        return self._model

    @property
    def template(self) -> PromptTemplate:
        return self._template

    async def extract(
        self,
        *,
        content: str,
        ask: str,
        request_next_links: bool = False,
        handler_candidates: list[LlmNextLink] | None = None,
        max_content_chars: int | None = None,
    ) -> ExtractionResult:
        """Run the template over (content, ask). Returns ExtractionResult.

        When a cache is wired and the key (hash(content), hash(ask), model_id,
        template_name) hits, the cached answer + tokens are returned with
        `cost_usd=0.0` and `original_cost_usd` carrying the original spend.

        v0.7 link-discovery — `request_next_links=True` appends a JSON
        next-links request to the user prompt. The response is split on
        `_NEXT_LINKS_FENCE_RE`; the answer is text before the fence and
        the JSON-array body inside the fence is parsed into `next_links`.
        Cache lookups bypass the next-links request entirely (the cached
        answer was produced without it; mixing them would yield empty
        candidates on hits).

        `handler_candidates` carries Tier-1 candidates the site handler
        produced; when non-empty, the prompt asks the LLM to re-rank /
        rewrite them against the question (Tier 1+2 composition).
        """
        cap = max_content_chars if max_content_chars is not None else self._max_content_chars
        truncated, was_truncated = _truncate(content, cap)
        raw_extras: dict[str, Any] | None = {"truncated": True} if was_truncated else None

        # Cache lookup uses the (truncated) content we'd actually send; that
        # way two callers with different upstream payloads but the same
        # post-cap content share a cache slot, mirroring WebFetch's behavior.
        # next-links extraction bypasses cache (skip when request_next_links).
        if self._cache is not None and not request_next_links:
            from .cache import hash_text

            content_hash = hash_text(truncated)
            ask_hash = hash_text(ask)
            hit = await self._cache.get(
                content_hash=content_hash,
                ask_hash=ask_hash,
                model_id=self._model.model,
                template_name=self._template.name,
            )
            if hit is not None:
                return ExtractionResult(
                    answer=hit.answer,
                    model=self._model.model,
                    template_name=self._template.name,
                    prompt_tokens=hit.prompt_tokens,
                    completion_tokens=hit.completion_tokens,
                    cost_usd=0.0,
                    latency_ms=0,
                    cache_hit=True,
                    original_cost_usd=hit.cost_usd,
                    raw=raw_extras,
                )

        user = self._template.user_template.format(content=truncated, ask=ask)
        if request_next_links:
            user = user + _next_links_suffix(handler_candidates)

        response = await self._provider.complete(
            system=self._template.system,
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )

        answer_text, parsed_next_links = _split_answer_and_next_links(response.text) if request_next_links else (response.text, [])

        # Persist a successful answer for re-use within the TTL window.
        # Skip cache write on next-links runs — the answer text alone (without
        # the JSON fence) is cached so a later non-next-links call still hits.
        if self._cache is not None and answer_text and not request_next_links:
            from .cache import hash_text

            await self._cache.put(
                content_hash=hash_text(truncated),
                ask_hash=hash_text(ask),
                model_id=self._model.model,
                template_name=self._template.name,
                answer=answer_text,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
            )

        return ExtractionResult(
            answer=answer_text,
            model=response.model,
            template_name=self._template.name,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            cache_hit=False,
            raw=raw_extras,
            next_links=parsed_next_links,
        )


def _truncate(content: str, cap: int) -> tuple[str, bool]:
    """Truncate to `cap` chars with a clear marker. Matches WebFetch's
    `BD_ = 100000` constant by default (research/123)."""
    if len(content) <= cap:
        return content, False
    return content[:cap] + f"\n\n[Content truncated to {cap} chars]\n", True


# --------------------------------------------------------------------- #
# Next-links prompt extension + response parser (v0.7 link-discovery)
# --------------------------------------------------------------------- #


_NEXT_LINKS_FENCE_RE = re.compile(
    r"```next_links\s*\n(?P<json>.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
_VALID_KINDS = frozenset({"drilldown", "related", "source"})


def _next_links_suffix(handler_candidates: list[LlmNextLink] | None) -> str:
    """Build the user-prompt suffix that requests the JSON next_links block.

    When `handler_candidates` is non-empty, the model is asked to re-rank,
    filter, and rewrite each `reason` against the question — Tier 1+2
    composition. Otherwise the model picks freely from links present in the
    markdown above.
    """
    intro = (
        "\n\n---\n\n"
        "Also identify up to 10 links present in the markdown above that would help "
        "answer the question better if fetched. Use the kinds: `drilldown` for the "
        "deeper layer of the same topic, `related` for sibling questions, `source` "
        "for citations. Reasons MUST be one phrase, ≤80 characters, naming something "
        "specific about THIS link (score, date, position). Return an empty array if "
        "the answer is already complete or no further links would help.\n\n"
    )
    if handler_candidates:
        listing = "\n".join(f"- [{c.anchor}]({c.url}) — reason: {c.reason}, kind: {c.kind}" for c in handler_candidates)
        intro += (
            "The site handler suggests these candidates. Re-rank them against the "
            "user's question, drop any that don't help, rewrite each `reason` to "
            "reflect question-relevance, and add candidates from the markdown if the "
            "handler missed an obvious one. Output ONLY the final list:\n\n"
            f"{listing}\n\n"
        )
    intro += (
        "Output the candidates as a JSON array inside a fenced block, AFTER your "
        "answer:\n\n"
        "```next_links\n"
        '[{"anchor":"...","url":"...","reason":"...","kind":"drilldown"}]\n'
        "```\n"
    )
    return intro


def _split_answer_and_next_links(text: str) -> tuple[str, list[LlmNextLink]]:
    """Split a response into (answer_text, next_links).

    Looks for a ```next_links ... ``` fenced block; everything before it is
    the answer, the JSON inside it is parsed. Invalid JSON or a missing
    fence yields (text-as-given, []). Entries with unknown `kind` or missing
    fields are silently dropped here — URL-must-be-in-markdown validation
    happens at the domain seam.
    """
    match = _NEXT_LINKS_FENCE_RE.search(text)
    if not match:
        return text, []
    answer = text[: match.start()].rstrip()
    try:
        parsed = json.loads(match.group("json"))
    except (ValueError, json.JSONDecodeError):
        return answer, []
    if not isinstance(parsed, list):
        return answer, []
    out: list[LlmNextLink] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        anchor = item.get("anchor")
        url = item.get("url")
        reason = item.get("reason")
        kind = item.get("kind")
        if not isinstance(anchor, str) or not isinstance(url, str) or not isinstance(reason, str):
            continue
        if not isinstance(kind, str) or kind not in _VALID_KINDS:
            continue
        out.append(LlmNextLink(anchor=anchor, url=url, reason=reason, kind=kind))
    return answer, out


__all__ = ["ExtractionResult", "Extractor", "LlmNextLink", "ModelSpec"]
