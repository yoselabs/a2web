"""The answer stage: the LLM call, and the one head that may re-enter it."""

from __future__ import annotations

import time

from ... import log as a2web_log
from ...events import StageEnded, StageStarted
from ...hints import (
    llm_unavailable_hint,
)
from ...link_digest import strip_handles
from ...models import Diagnostic, ExtractionMeta, Verdict
from ...state import AppState, ResourceUnavailable
from ..answer.digest import _build_link_digest, _rehydrate_routing_handles
from ..answer.links import _to_llm_next_link, _validate_llm_next_links_against_markdown
from ..answer.obstacle import _phase_listing_render, _phase_obstacle_render
from ..comprehension.menu import assemble_menu
from ..context import FetchContext
from ..sufficiency.completeness import _apply_llm_listing_oracle


async def _phase_answer(fc: FetchContext, *, state: AppState) -> None:
    """The answer, and the two renders that can invalidate it — one head, one caller.

    `_phase_extract_answer` was entered from THREE places and is not idempotent,
    which is the design's "answer is being used as the loop body". The
    re-entries were correct; what was wrong is that they were invisible. Each
    render phase decided for itself whether the answer needed recomputing, so
    "how many LLM calls does a fetch make" was a property of which phases
    happened to fire, answerable only by reading three functions.

    Both renders run BEFORE `_phase_cache_write`, so the final (possibly
    re-rendered) body is the one cached and a confabulated shell never lands in
    the cache. The sequence is exactly the previous one — answer, obstacle
    render, answer-if-changed, listing render, answer-if-changed — hoisted, not
    reordered. Deliberately NOT a `while` loop: that would re-run the obstacle
    render after a listing render changed the content, which is a second render
    nobody asked for.

    What this does not fix, because it is a behaviour change and this is a move:
    a second entry OVERWRITES `fc.extraction_meta`, so a fetch that made two LLM
    calls reports the tokens and cost of one. Filed in `BACKLOG.md`.
    """
    await _phase_extract_answer(fc, state=state)
    # Obstacle-driven render: the extractor flagged an empty/blocked obstacle (a
    # fat SPA shell that passed the gate) — one paid render, then re-answer over
    # the real content.
    if await _phase_obstacle_render(fc, state=state):
        await _phase_extract_answer(fc, state=state)
    # Listing scroll-to-complete: a partial listing plus `complete_listings` —
    # one bounded scrolling render (sharing the obstacle/wall paid budget), then
    # re-answer over the fuller page.
    if await _phase_listing_render(fc, state=state):
        await _phase_extract_answer(fc, state=state)


async def _phase_extract_answer(
    fc: FetchContext,
    *,
    state: AppState,
) -> None:
    """Run server-side LLM extraction when ask= is set. v0.4.

    Resolves `Lazy[LlmExtractorResource]` at this seam — the LLM resource
    only enters when an `ask=` was passed AND the fetch succeeded.
    """
    if fc.ask is None:
        return
    # A corroborated complete-small-page (`small_page_confirmed`) is thin — its
    # verdict is left `length_floor` (so cache declines it) — but it IS extractable:
    # the whole point of the promotion is that the extractor runs on the real body.
    # So the ok-verdict gate is relaxed for it; every other non-ok verdict still
    # skips extraction (no content, or a genuine wall).
    if (fc.resolved_verdict() is not Verdict.ok and not fc.small_page_confirmed) or not fc.content_md:
        # Failed fetches don't get extraction — no content to extract from.
        # The agent will see status=failed + diagnostics_summary explaining why.
        return
    phase_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2web_log.info(StageStarted(t_ms=phase_start_ms, step="extract_answer"))

    # v0.7 link-discovery: request next-links from the LLM in the same call.
    # Skip the extension when the off-switch is engaged.
    request_next_links = fc.next_links_enabled
    handler_candidates_for_llm = (
        [_to_llm_next_link(nl) for nl in fc.next_links_handler] if request_next_links and fc.next_links_handler else None
    )

    # Feed Haiku the full menu (prose + json_synth + record_synth), not the
    # single quality-picked `content_md` (ADR-0005). The menu is assembled
    # deterministically so the prompt-cache prefix stays byte-stable across
    # asks. Handler/pre-rendered pages skip the escalation ladder, leaving
    # `content_candidates` empty — fall back to `content_md` there.
    menu = assemble_menu(fc.content_candidates) or fc.content_md

    # v1 link-affordances: feed the extractor the page's real links so `other_pages`
    # references a `{{n}}` handle instead of guessing a URL. Gated on a pre-LLM
    # product/listing proxy (structural_form is post-hoc) — the presence of a
    # json_synth (product schema) or record_synth (listing) candidate. Article
    # fetches pay nothing.
    fc.link_digest = _build_link_digest(fc)
    digest_text = fc.link_digest.render() if fc.link_digest else None

    # One unavailability path: resolving the resource (not provisioned) and
    # awaiting the injected provider inside extract() (no provider configured)
    # both raise ResourceUnavailable. Graceful degrade — the fetch succeeded,
    # the operator hint surfaces the actionable reason.
    try:
        extractor_resource = await fc.llm_extractor()
        result = await extractor_resource.extract(
            content=menu,
            ask=fc.ask,
            request_next_links=request_next_links,
            handler_candidates=handler_candidates_for_llm,
            max_content_chars=fc.max_content_chars,
            request_routing=fc.include_routing,
            link_digest=digest_text,
        )
    except ResourceUnavailable as exc:
        fc.operator_hints.append(llm_unavailable_hint(reason=exc.reason, key_env=state.settings.llm_api_key_env))
        dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
        await a2web_log.info(
            StageEnded(
                t_ms=phase_start_ms,
                step="extract_answer",
                verdict=Verdict.other,
                dur_ms=dur_ms,
                extra={"skipped": "llm_unavailable"},
            ),
        )
        return
    # Rehydration of the answer text: if the model referenced a link by its
    # `{{n}}` handle inside its prose (not just in `other_pages`), turn that
    # handle into the real URL rather than leaking `{{n}}` to the caller. Known
    # handle -> href (an actionable inline link); unknown handle -> removed.
    #
    # The no-digest branch STRIPS rather than passing through, and that was a
    # real leak until 2026-08-03. It read "no-op when no digest was fed", which
    # sounds safe and is not: `_build_link_digest` returns None for a prose-only
    # article, while the `LINKS IN THE ANSWER` clause teaching the `{{n}}`
    # convention lives in the BASE prompt and ships unconditionally. The model
    # was taught the convention, given no link list, and anything it emitted
    # reached the caller verbatim. A handle with no digest cannot resolve to
    # anything, so it is removed — one rule, true in both branches.
    #
    # Also the seam a future "links in the answer" eval builds on
    # (findings 2026-07-11-answer-inline-links).
    fc.extracted_answer = fc.link_digest.rehydrate_text(result.answer) if fc.link_digest else strip_handles(result.answer)
    # Carry the provider failure (if any) to the response builder so the
    # unanswered-ask hint can name the real cause instead of blaming the page.
    fc.extraction_provider_error = result.provider_error
    fc.extraction_provider_error_retryable = result.provider_error_retryable

    # v0.7 link-discovery: validate LLM-supplied URLs against the markdown
    # the LLM was given. URLs not present in the content are dropped with a
    # drift diagnostic — defense against hallucinated URLs. Handler-supplied
    # URLs (re-rank flow) are exempt: they were in the prompt context, not
    # the markdown, but came from a trusted upstream source.
    if request_next_links and result.next_links:
        validated, dropped = _validate_llm_next_links_against_markdown(
            result.next_links,
            markdown=fc.content_md,
            handler_urls={nl.url for nl in fc.next_links_handler},
        )
        fc.next_links_llm = validated
        for drift_url in dropped:
            fc.diagnostics.append(
                Diagnostic(
                    t_ms=int((time.perf_counter() - fc.start_perf) * 1000),
                    step="extract_answer.next_links",
                    verdict=Verdict.other,
                    dur_ms=0,
                    extra={"event": "extraction_drift", "url": drift_url},
                ),
            )

    fc.extraction_meta = ExtractionMeta(
        model=result.model,
        template_name=result.template_name,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cache_hit=result.cache_hit,
        truncated=bool(result.raw and result.raw.get("truncated")),
    )
    # v0.21 — surface the router-shape payload for the seam projector. When
    # the model returned malformed JSON or `include_routing=False`, this is
    # None. v1 link-affordances: rehydrate `{{n}}` handles → real hrefs against
    # the closed digest set (unknown handles dropped, never guessed).
    fc.routing = _rehydrate_routing_handles(result.routing, fc.link_digest)
    fc.routing_outcome = result.routing_outcome
    # LLM-side partialness detection (superset of the regex oracle) now that the
    # model's `item_total_seen` is available — closes the noun-list language gap.
    _apply_llm_listing_oracle(fc)
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
    await a2web_log.info(
        StageEnded(
            t_ms=phase_start_ms,
            step="extract_answer",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
        ),
    )
