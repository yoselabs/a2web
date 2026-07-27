"""Extractor — runs an LLM over (content, ask) to produce an answer string.

This is the server-side extraction trick that Claude Code's WebFetch uses
internally: the calling agent never sees the page, only the answer. See
`prompts.WEBFETCH_DEFAULT_V1` for the byte-identical template.

Tied to a `Provider` + `PromptTemplate` at construction time. The cache
(extraction-answer LRU) lands in a follow-up commit.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from anyllm import AnyLLMError, Completion
from anyllm import LLMProvider as Provider

from .prompts import EXTRACT_ROUTER_V1, WEBFETCH_DEFAULT_V1, PromptTemplate
from .router_payload import OtherPageBoundary, RefinementAxisBoundary, RouterPayload
from .wobble import (
    EXTRACTOR_ROUTING_POLICY,
    ParseError,
    Wobbled,
    WobbleTolerance,
    emit_wobble,
    parse_list_with_policy,
    parse_with_policy,
    strip_fenced_blocks,
    unwrap,
)

if TYPE_CHECKING:
    from llm_cache import LlmCache

# Emit on the `a2web` logger by NAME rather than importing `a2web.log` —
# `packages/` may not import from `a2web.<domain>` (tach.toml). The record
# shape is identical to what `a2web.log` produces (message + `fields` payload),
# so the same sinks drain it; only the import is avoided. A bare logger name is
# the smallest possible coupling to the host app. Mirrors `wobble/_internal.py`.
_LOG = logging.getLogger("a2web")

# Cap the provider-error text on the log event; the full string still rides
# `ExtractionResult.provider_error` to the operator hint.
_PROVIDER_ERROR_MAX = 500


@dataclass(slots=True)
class ModelSpec:
    """Identifies the LLM to call by model id.

    The provider *instance* is held separately (on the Extractor / Judge);
    `ModelSpec` only carries the model-id string, which is the wire arg to
    `provider.complete(model=...)` and the extraction-cache key.
    """

    model: str


class RoutingOutcome(StrEnum):
    """What happened to a requested router-shape envelope.

    Replaces a `routing_lost: bool` that collapsed three unlike events into
    one. They have different causes and different correct responses, so a
    consumer that can only ask "was it lost?" is forced to guess:

    - `RECOVERED` — an envelope parsed and carried a payload. The normal case.
    - `UNPARSABLE` — no envelope survived, even after fence tolerance. The
      answer is whatever prose could be salvaged; there is no index at all.
    - `UNCLASSIFIED` — the envelope parsed and `answer` is intact, but the model
      omitted `structural_form`/`shape`. The index may still be fully present:
      classification and index are independent, and conflating them is what
      used to discard a perfectly good index alongside a missing label.
    - `PROVIDER_ERROR` — the call never produced text. Already reported via
      `provider_error`; it is a member here rather than an exclusion because the
      extractor genuinely reaches this state, and a type that cannot express it
      pushes the distinction back into ad-hoc booleans at the call site. Its
      CONSUMERS exclude it, so degradation is not double-reported.
    """

    RECOVERED = "recovered"
    UNPARSABLE = "unparsable"
    UNCLASSIFIED = "unclassified"
    PROVIDER_ERROR = "provider_error"


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
    # Set ONLY when the provider call itself failed (`AnyLLMError`). An empty
    # `answer` is ambiguous on its own — a genuine on-contract empty, a parse
    # failure, and a dead backend all look identical — so this field is what
    # lets the orchestrator tell the caller a truthful story. `None` on every
    # success AND on a genuine empty answer.
    provider_error: str | None = None
    # Whether the failed provider call is worth retrying (anyllm classifies it).
    # Meaningless unless `provider_error` is set.
    provider_error_retryable: bool = False
    # What happened to the routing envelope. `None` when routing was never
    # requested — distinct from every failure arm, and the distinction the old
    # `routing_lost: bool` could not draw. See `RoutingOutcome`.
    routing_outcome: RoutingOutcome | None = None


class Extractor:
    """Compose a Provider + PromptTemplate into a single `.extract()` call.

    Usage:
        # The provider is resolved upstream (a2web's `select_provider`) and
        # injected — never constructed inline here, which would bypass the
        # manifest registry's availability gating.
        ex = Extractor(
            provider=provider,
            model=ModelSpec("claude-haiku-4-5-20251001"),
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
        cache: LlmCache | None = None,
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
        link_digest: str | None = None,
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
            from llm_cache import make_key

            cache_key = make_key(truncated, ask, active_template.name)
            hit = await self._cache.get(key=cache_key, model=self._model.model)
            if hit is not None:
                return ExtractionResult(
                    answer=hit.text,
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
        # Append to `tail` only — keeps `cache_prefix` byte-stable so cache hits
        # aren't lost. Tail varies per-call already; these are just more per-call
        # variation. The link digest rides here (not the cache prefix) so the
        # ~95% no-digest path keeps the same prompt-cache slot.
        tail_suffix = ""
        # ONE output contract per call. `request_routing` wins: the router
        # template already says "Output strict JSON only" and carries
        # `other_pages`, so also appending the fence suffix asks the model for a
        # second, differently-shaped contract ("fenced block, AFTER your
        # answer"). `query` sets BOTH flags, models obeyed whichever they read
        # last, the router parse then raised, and the raw prose+fence shipped as
        # `answer`. The flags stay independent in the signature — only prompt
        # construction resolves the precedence.
        if request_next_links and not request_routing:
            tail_suffix += _next_links_suffix(handler_candidates)
        if link_digest:
            tail_suffix += _link_digest_suffix(link_digest)
        if tail_suffix:
            from .prompts import PromptParts

            parts = PromptParts(
                system=parts.system,
                cache_prefix=parts.cache_prefix,
                tail=parts.tail + tail_suffix,
            )
        user = parts.cache_prefix + parts.tail if parts.cache_prefix else parts.tail

        # anyllm providers are fail-loud: any provider/API failure raises
        # `AnyLLMError` instead of returning an empty-text result. a2web's
        # extractor historically degraded on error — the local providers
        # translated API errors into a `ProviderResponse(text="", raw={"error":
        # ...})` and the orchestrator's "empty answer → degrade to raw + operator
        # hint" path took over. Preserve that seam: catch `AnyLLMError` and rebuild
        # the same empty-answer Completion the old providers produced, so nothing
        # downstream (that never previously saw an exception) starts seeing one.
        provider_error: str | None = None
        provider_error_retryable = False
        try:
            response = await self._provider.complete(
                system=active_template.system,
                user=user,
                model=self._model.model,
                max_tokens=self._max_tokens,
                thinking_disabled=True,
                parts=parts,
            )
        except AnyLLMError as exc:
            # Keep the degrade seam (callers downstream never saw an exception
            # here and must not start), but no longer let the cause evaporate:
            # log it, and carry it out on `ExtractionResult.provider_error` so
            # the operator hint can name the real failure instead of blaming the
            # page or the question.
            provider_error = str(exc)
            provider_error_retryable = bool(getattr(exc, "retryable", False))
            _LOG.warning(
                "llm_provider_error",
                extra={
                    "fields": {
                        "model": self._model.model,
                        "template": active_template.name,
                        "error": provider_error[:_PROVIDER_ERROR_MAX],
                        "retryable": provider_error_retryable,
                        "hint": str(getattr(exc, "hint", "") or ""),
                    }
                },
            )
            response = Completion(text="", model=self._model.model, raw={"error": provider_error})

        routing_payload: RouterPayload | None = None
        routing_outcome: RoutingOutcome | None = None
        if request_routing:
            answer_text, routing_wobbled = _split_answer_and_routing(response.text, model=self._model.model)
            if routing_wobbled is not None:
                routing_result: _RoutingResult = unwrap(routing_wobbled)
                routing_payload = routing_result.payload
            # Which arm, and in this order: a dead provider produced no text to
            # parse, so its unparsable-looking result is not an LLM formatting
            # fact and must not be reported as one.
            if provider_error is not None:
                routing_outcome = RoutingOutcome.PROVIDER_ERROR
            elif routing_payload is None:
                routing_outcome = RoutingOutcome.UNPARSABLE
            elif routing_payload.structural_form is None or routing_payload.shape is None:
                routing_outcome = RoutingOutcome.UNCLASSIFIED
            else:
                routing_outcome = RoutingOutcome.RECOVERED
            parsed_next_links: list[LlmNextLink] = []
        elif request_next_links:
            answer_text, parsed_next_links = _split_answer_and_next_links(response.text, model=self._model.model)
            answer_text = strip_fenced_blocks(answer_text)
        else:
            answer_text, parsed_next_links = response.text, []

        # Persist a successful answer for re-use within the TTL window.
        # Skip cache write on next-links / routing runs — the answer text
        # alone (without the JSON envelope) is cached so a later plain call
        # still hits.
        if self._cache is not None and answer_text and not request_next_links and not request_routing:
            from llm_cache import make_key

            # On this path answer_text == response.text (no routing/next_links
            # split), so the Completion carries the exact text being cached along
            # with its original cost/token/latency accounting.
            await self._cache.put(
                key=make_key(truncated, ask, active_template.name),
                model=self._model.model,
                completion=response,
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
            routing_outcome=routing_outcome,
            provider_error=provider_error,
            provider_error_retryable=provider_error_retryable,
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


def _link_digest_suffix(link_digest: str) -> str:
    """Append the page's real links so `other_pages` can reference them by handle.

    The digest is a closed list of `{{n}} <label> · <path>` lines. The model
    references a link by its handle (`{"handle": 3, ...}`); the server supplies
    the real URL, so the model can never emit a URL it did not see — the exact
    hole that made the old "must appear verbatim" rule unsatisfiable (the page's
    links were never in the content). Selection over the set follows the
    extend-the-primary-entity principle stated in the router schema.
    """
    return "\n\n---\n\n" + link_digest + "\n"


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


def _split_answer_and_next_links(text: str, *, model: str = "unknown") -> tuple[str, list[LlmNextLink]]:
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


def _note_malformed(field: str, value: Any, model: str) -> None:
    """Report a field that was PRESENT but the wrong shape.

    The funnel's policies only fire on ABSENCE — a field present with a wrong
    type never reaches them, so the coercions below (`also_here` that is a
    string, `other_pages` that is a dict) used to drop real content in total
    silence. That silence was tolerable only while every absence was also being
    reported; now that the five optional fields are `OPTIONAL`, it would be the
    only remaining way for the model to lose an index without saying so.

    The distinction is exactly the one `OPTIONAL` draws: absent-by-contract is
    normal and silent, present-but-corrupt is a wobble and reports.
    """
    emit_wobble(
        boundary="extractor.router_shape",
        field=field,
        tolerance=WobbleTolerance.DEFAULT,
        model=model,
        raw_excerpt=repr(value),
    )


def _build_router_payload(parsed: dict[str, Any], *, model: str = "unknown") -> _RoutingResult:
    """Funnel `into` callable. Funnel guarantees `answer` is present (STRICT);
    everything else is best-effort and never costs the caller the answer.

    **The index is parsed unconditionally, BEFORE the classification is
    judged.** It used to return `payload=None` the moment `structural_form` or
    `shape` was missing — several statements above `also_here` / `other_pages`
    were ever read — so a model that supplied a perfectly good index and merely
    forgot the label had that index thrown away with it. Classification and
    index are independent facts about the page: only the options shelf needs
    the classification, and it gates on it separately (a `None` classification
    suppresses the shelf exactly as an unsuitable one does). ADR-0015: a
    withheld body must still leave its index.
    """
    answer = parsed["answer"]
    if not isinstance(answer, str) or not answer:
        raise ParseError("extractor.router_shape: empty answer")

    structural_form_raw = parsed.get("structural_form")
    structural_form = structural_form_raw if isinstance(structural_form_raw, str) and structural_form_raw else None
    shape_raw = parsed.get("shape")
    shape = shape_raw if isinstance(shape_raw, str) and shape_raw else None

    obstacle_raw = parsed.get("obstacle")
    obstacle = obstacle_raw if isinstance(obstacle_raw, str) and obstacle_raw else None

    also_here_raw = parsed.get("also_here", ())
    if isinstance(also_here_raw, list):
        also_here: tuple[str, ...] = tuple(q for q in also_here_raw if isinstance(q, str) and q)
    else:
        also_here = ()
        if also_here_raw:
            _note_malformed("also_here", also_here_raw, model)

    other_pages: list[OtherPageBoundary] = []
    other_pages_raw = parsed.get("other_pages", ())
    if other_pages_raw and not isinstance(other_pages_raw, list):
        _note_malformed("other_pages", other_pages_raw, model)
    if isinstance(other_pages_raw, list):
        for item in other_pages_raw:
            if not isinstance(item, dict):
                continue
            reason_raw = item.get("reason", "")
            reason = reason_raw if isinstance(reason_raw, str) else ""
            # `kind` defaults to drilldown (the question-conditioned case); a
            # value outside the closed set falls back to drilldown here and is
            # re-validated by the pydantic mirror at the domain seam.
            kind_raw = item.get("kind")
            kind = kind_raw if isinstance(kind_raw, str) and kind_raw in ("structural", "drilldown") else "drilldown"
            # Preferred (digest path): a `{{n}}` handle the domain seam
            # rehydrates from the closed link set. Fall back to a raw `url`
            # (legacy / no-digest pages).
            handle_val = item.get("handle")
            if isinstance(handle_val, int) and not isinstance(handle_val, bool):
                other_pages.append(OtherPageBoundary(url="", reason=reason, kind=kind, handle=handle_val))
                continue
            url_val = item.get("url")
            if isinstance(url_val, str) and url_val:
                other_pages.append(OtherPageBoundary(url=url_val, reason=reason, kind=kind))

    axes: list[RefinementAxisBoundary] = []
    axes_raw = parsed.get("refinement_axes", ())
    if axes_raw and not isinstance(axes_raw, list):
        _note_malformed("refinement_axes", axes_raw, model)
    if isinstance(axes_raw, list):
        for item in axes_raw:
            if not isinstance(item, dict):
                continue
            dimension = item.get("dimension")
            if not isinstance(dimension, str) or not dimension:
                continue
            how = item.get("how", "")
            axes.append(RefinementAxisBoundary(dimension=dimension, how=how if isinstance(how, str) else ""))

    total_seen_raw = parsed.get("item_total_seen")
    item_total_seen = total_seen_raw if isinstance(total_seen_raw, int) and not isinstance(total_seen_raw, bool) else None

    payload = RouterPayload(
        answer=answer,
        structural_form=structural_form,
        shape=shape,
        obstacle=obstacle,
        also_here=also_here,
        other_pages=tuple(other_pages),
        refinement_axes=tuple(axes),
        item_total_seen=item_total_seen,
    )
    return _RoutingResult(answer=answer, payload=payload)


def _split_answer_and_routing(text: str, *, model: str = "unknown") -> tuple[str, Wobbled | None]:
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
            into=lambda parsed: _build_router_payload(parsed, model=model),
            boundary="extractor.router_shape",
            model=model,
        )
    except ParseError:
        # NEVER return the raw model response as the answer. This is the exact
        # mechanism by which a ```next_links fence reached the wire: the router
        # parse raised and the whole response — prose plus scaffolding — became
        # `answer`. The spec always said "the successfully parsed answer text";
        # the raw dump was never what was specified.
        _LOG.warning(
            "llm_wobble",
            extra={
                "fields": {
                    "boundary": "extractor.router_shape",
                    "field": "__envelope__",
                    "policy_applied": "skip",
                    "model": model,
                    "raw_excerpt": text[:200],
                }
            },
        )
        return strip_fenced_blocks(text), None
    result: _RoutingResult = unwrap(wobbled)
    return strip_fenced_blocks(result.answer), wobbled


__all__ = ["ExtractionResult", "Extractor", "LlmNextLink", "ModelSpec"]
