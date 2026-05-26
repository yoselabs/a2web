"""Extractor — runs an LLM over (content, ask) to produce an answer string.

This is the server-side extraction trick that Claude Code's WebFetch uses
internally: the calling agent never sees the page, only the answer. See
`prompts.WEBFETCH_DEFAULT_V1` for the byte-identical template.

Tied to a `Provider` + `PromptTemplate` at construction time. The cache
(extraction-answer LRU) lands in a follow-up commit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .prompts import EXTRACT_ROUTER_V1, WEBFETCH_DEFAULT_V1, PromptTemplate
from .providers.base import Provider
from .router_payload import NextUrlBoundary, RouterPayload
from .wobble import (
    EXTRACTOR_ROUTING_POLICY,
    ParseError,
    Wobbled,
    parse_list_with_policy,
    parse_with_policy,
    unwrap,
)

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
    routing: RouterPayload | None = None


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
        request_routing: bool = False,
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
        # When routing is requested, swap to the router-shape template for THIS
        # call only — the constructor-bound default template is unchanged.
        # cache_prefix_template is byte-identical between the two templates, so
        # the v0.19 cache invariant survives the swap.
        active_template = EXTRACT_ROUTER_V1 if request_routing else self._template

        cap = max_content_chars if max_content_chars is not None else self._max_content_chars
        truncated, was_truncated = _truncate(content, cap)
        raw_extras: dict[str, Any] | None = {"truncated": True} if was_truncated else None

        # Cache lookup uses the (truncated) content we'd actually send; that
        # way two callers with different upstream payloads but the same
        # post-cap content share a cache slot, mirroring WebFetch's behavior.
        # Skip cache when routing or next-links are requested — the cached
        # answer was produced without them; mixing would yield empty payloads
        # on hits.
        if self._cache is not None and not request_next_links and not request_routing:
            from .cache import hash_text

            content_hash = hash_text(truncated)
            ask_hash = hash_text(ask)
            hit = await self._cache.get(
                content_hash=content_hash,
                ask_hash=ask_hash,
                model_id=self._model.model,
                template_name=active_template.name,
            )
            if hit is not None:
                return ExtractionResult(
                    answer=hit.answer,
                    model=self._model.model,
                    template_name=active_template.name,
                    prompt_tokens=hit.prompt_tokens,
                    completion_tokens=hit.completion_tokens,
                    cost_usd=0.0,
                    latency_ms=0,
                    cache_hit=True,
                    original_cost_usd=hit.cost_usd,
                    raw=raw_extras,
                )

        parts = active_template.render(content=truncated, ask=ask)
        if request_next_links:
            # Append to `tail` only — keeps `cache_prefix` byte-stable so cache
            # hits aren't lost. Tail varies per-call already; the next-links
            # request is just another per-call variation.
            from .prompts import PromptParts

            parts = PromptParts(
                system=parts.system,
                cache_prefix=parts.cache_prefix,
                tail=parts.tail + _next_links_suffix(handler_candidates),
            )
        user = parts.cache_prefix + parts.tail if parts.cache_prefix else parts.tail

        response = await self._provider.complete(
            system=active_template.system,
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
            parts=parts,
        )

        routing_payload: RouterPayload | None = None
        if request_routing:
            answer_text, routing_wobbled = _split_answer_and_routing(
                response.text, model=self._model.model
            )
            if routing_wobbled is not None:
                routing_result: _RoutingResult = unwrap(routing_wobbled)
                routing_payload = routing_result.payload
            parsed_next_links: list[LlmNextLink] = []
        elif request_next_links:
            answer_text, parsed_next_links = _split_answer_and_next_links(
                response.text, model=self._model.model
            )
        else:
            answer_text, parsed_next_links = response.text, []

        # Persist a successful answer for re-use within the TTL window.
        # Skip cache write on next-links / routing runs — the answer text
        # alone (without the JSON envelope) is cached so a later plain call
        # still hits.
        if self._cache is not None and answer_text and not request_next_links and not request_routing:
            from .cache import hash_text

            await self._cache.put(
                content_hash=hash_text(truncated),
                ask_hash=hash_text(ask),
                model_id=self._model.model,
                template_name=active_template.name,
                answer=answer_text,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
            )

        return ExtractionResult(
            answer=answer_text,
            model=response.model,
            template_name=active_template.name,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            cache_hit=False,
            raw=raw_extras,
            next_links=parsed_next_links,
            routing=routing_payload,
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


def _next_link_from_entry(entry: dict[str, Any]) -> LlmNextLink | None:
    """Per-item filter for the next_links JSON array.

    Returns None to silently drop entries with unknown `kind` or missing
    fields — the funnel logs them as recovered. URL-must-be-in-markdown
    validation happens at the domain seam, not here.
    """
    anchor = entry.get("anchor")
    url = entry.get("url")
    reason = entry.get("reason")
    kind = entry.get("kind")
    if not isinstance(anchor, str) or not isinstance(url, str) or not isinstance(reason, str):
        return None
    if not isinstance(kind, str) or kind not in _VALID_KINDS:
        return None
    return LlmNextLink(anchor=anchor, url=url, reason=reason, kind=kind)


def _split_answer_and_next_links(
    text: str, *, model: str = "unknown"
) -> tuple[str, list[LlmNextLink]]:
    """Split a response into (answer_text, next_links) via the wobble funnel.

    Looks for a ```next_links ... ``` fenced block. Everything before is the
    answer; the JSON array inside is funneled through `parse_list_with_policy`
    so malformed entries fire `llm_wobble` events instead of disappearing
    silently.
    """
    match = _NEXT_LINKS_FENCE_RE.search(text)
    if not match:
        return text, []
    answer = text[: match.start()].rstrip()
    try:
        wobbled = parse_list_with_policy(
            match.group("json"),
            item=_next_link_from_entry,
            boundary="extractor.next_links",
            model=model,
            strip_fences=False,
        )
    except ParseError:
        return answer, []
    parsed: list[LlmNextLink] = unwrap(wobbled)
    return answer, parsed


# --------------------------------------------------------------------- #
# Router-shape parsing (v0.21 — request_routing path)
# --------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _RoutingResult:
    """`into` payload — separates the salvaged answer from the routing payload
    so the funnel-caller can degrade routing while keeping the answer."""

    answer: str
    payload: RouterPayload | None


def _build_router_payload(parsed: dict[str, Any]) -> _RoutingResult:
    """Funnel `into` callable. Funnel guarantees `answer` is present (STRICT);
    structural_form/shape are surfaced as-is and validated here so the answer
    survives when routing fields are degraded."""
    answer = parsed["answer"]
    if not isinstance(answer, str) or not answer:
        raise ParseError("extractor.router_shape: empty answer")

    structural_form = parsed.get("structural_form")
    shape = parsed.get("shape")
    if not isinstance(structural_form, str) or not structural_form:
        return _RoutingResult(answer=answer, payload=None)
    if not isinstance(shape, str) or not shape:
        return _RoutingResult(answer=answer, payload=None)

    genre_raw = parsed.get("genre")
    genre = genre_raw if isinstance(genre_raw, str) and genre_raw else None
    obstacle_raw = parsed.get("obstacle")
    obstacle = obstacle_raw if isinstance(obstacle_raw, str) and obstacle_raw else None

    ask_here_raw = parsed.get("ask_here", ())
    ask_here: tuple[str, ...] = (
        tuple(q for q in ask_here_raw if isinstance(q, str) and q)
        if isinstance(ask_here_raw, list)
        else ()
    )

    try_urls: list[NextUrlBoundary] = []
    try_url_raw = parsed.get("try_url", ())
    if isinstance(try_url_raw, list):
        for item in try_url_raw:
            if not isinstance(item, dict):
                continue
            url_val = item.get("url")
            if not isinstance(url_val, str) or not url_val:
                continue
            reason = item.get("reason", "")
            try_urls.append(
                NextUrlBoundary(url=url_val, reason=reason if isinstance(reason, str) else "")
            )

    payload = RouterPayload(
        answer=answer,
        structural_form=structural_form,
        shape=shape,
        genre=genre,
        obstacle=obstacle,
        ask_here=ask_here,
        try_url=tuple(try_urls),
    )
    return _RoutingResult(answer=answer, payload=payload)


def _split_answer_and_routing(
    text: str, *, model: str = "unknown"
) -> tuple[str, Wobbled | None]:
    """Parse the router-shape JSON envelope through the wobble funnel.

    Returns `(answer_text, Wobbled | None)` — Wobbled wraps a `_RoutingResult`.
    Malformed JSON or missing `answer` yields `(text-as-given, None)`. Missing
    `structural_form`/`shape` yields `(answer, wobbled_with_payload_none)` —
    the answer is preserved; routing is degraded.
    """
    try:
        wobbled = parse_with_policy(
            text,
            policies=EXTRACTOR_ROUTING_POLICY,
            into=_build_router_payload,
            boundary="extractor.router_shape",
            model=model,
        )
    except ParseError:
        return text, None
    result: _RoutingResult = unwrap(wobbled)
    return result.answer, wobbled


__all__ = ["ExtractionResult", "Extractor", "LlmNextLink", "ModelSpec"]
