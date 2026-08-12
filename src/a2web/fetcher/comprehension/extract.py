"""Extraction over the retrieved body, or the pre-rendered payload."""

from __future__ import annotations

import time
from dataclasses import dataclass as _dc
from datetime import date

from content_extract import (
    extract_markdown as _package_extract_markdown,
)
from content_extract import (
    parse_metadata,
)
from json_in_html import (
    is_json_content_type,
    parse_json_response,
)

from ... import log as a2web_log
from ...events import StageEnded, StageStarted
from ...models import Diagnostic, Heading, Link, Verdict
from ...packages.structured_render import json_response_fallback, json_to_markdown_rows
from ...tiers import Rendered
from ..comprehension.ladder import _run_extraction_escalation
from ..context import FetchContext
from ..retrieval.install import _install_rendered_fields
from ..sufficiency.completeness import _phase_listing_completeness
from ..sufficiency.gated_sections import _phase_gated_sections


def _is_sentinel_date(d: date) -> bool:
    """True for a bare Jan-1 date (a2web-7bj.9).

    `content_extract`/trafilatura's `published` never carries a time
    component (`_parse_date` truncates to `YYYY-MM-DD`), so "Jan-1 with no
    time" collapses to one testable fact: month/day == 1/1. Observed twice in
    the same live session — 2018-01-01 on dhl.com, 2000-01-01 on
    gumruk.dhl.com.tr — both copyright-footer/schema-boilerplate artifacts,
    not genuine first-published dates. A page genuinely first published on
    Jan 1 is rare enough that treating the ambiguous case as "no reliable
    date" (never shipping it) is safer than shipping a sentinel that silently
    mis-sorts anything ranking by recency.
    """
    return d.month == 1 and d.day == 1


@_dc(slots=True)
class _ExtractResult:
    """Domain-typed wrapper over `content_extract.ExtractedContent` (shelf)."""

    content_md: str
    title: str | None
    byline: str | None
    published: date | None
    headings: list[Heading]
    links: list[Link]
    score: float | None


async def extract_markdown(html: str, url: str) -> _ExtractResult:
    """Run package extract, map frozen dataclasses → pydantic Heading/Link."""
    raw = await _package_extract_markdown(html, url)
    return _ExtractResult(
        content_md=raw.content_md,
        title=raw.title,
        byline=raw.byline,
        published=raw.published,
        headings=[Heading(level=h.level, text=h.text) for h in raw.headings],
        links=[Link(anchor=lk.anchor, href=lk.href, role=lk.role) for lk in raw.links],
        score=raw.score,
    )


async def _phase_extract(fc: FetchContext) -> None:
    """Run extraction on `body` (or use pre-rendered handler output)."""
    extract_dur_start = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
    raw_html = fc.body.decode("utf-8", errors="replace") if fc.body else ""

    if fc.pre_rendered_payload is not None:
        # Site handler / archive / browser already ran the canonical extractor;
        # skip the second pass.
        #
        # THE SKIP IS SCOPED TO CONTENT EXTRACTION AND METADATA. `extract_markdown`,
        # `parse_metadata` and the date finders are what a pre-rendering tier has
        # already paid for, and they stay skipped — that is the whole optimisation.
        # The structured ladder below is NOT trafilatura: it is `json_in_html` plus
        # `record_mine` over the same bytes, which no tier has run. Skipping it too
        # (which this branch did until 2026-07-28, purely because those calls sat
        # textually below the early return) starved four consumers on every fetch
        # whose tier WON the loop with a pre-rendered payload:
        #
        #   fc.content_candidates  → the extractor's menu collapsed to one item,
        #                            voiding the ADR-0005 collect-every-rung contract
        #   json_synth/record_synth → `_build_link_digest`'s gate was unsatisfiable,
        #                            so `other_pages` could never be emitted here
        #   fc.record_count        → `listing_partial` could never fire, i.e.
        #                            ADR-0009's sufficiency axis was off on exactly
        #                            the population that forced a browser BECAUSE
        #                            it was an infinite-scroll listing
        #   fc.record_set          → the rank-don't-skip option shelf stayed empty
        #
        # The escalation install paths (`_escalate_browser` / `_escalate_paid`)
        # already ran the ladder themselves; this brings the tier-loop-win path
        # into line with them. See `eval/findings_2026-07-28.md`.
        #
        # Pinned by `tests/capabilities/tier_pipeline/test_pre_rendered_skip_boundary.py`,
        # which asserts BOTH halves: the ladder runs, and no `extract` row appears.
        _install_rendered_fields(fc, fc.pre_rendered_payload)
        # Seeds its baseline candidate from `fc.content_md`, assigned just above —
        # so the menu has the same shape here as on the raw path, with no second
        # parse. Each rung self-gates, so a non-HTML pre-rendered body (a JSON API
        # payload, jina's markdown) produces nothing and costs only its own
        # precondition check: measured at 0.16 ms, against 2.9 ms on a real
        # listing DOM.
        await _run_extraction_escalation(fc, raw_html=raw_html)
        _phase_listing_completeness(fc, raw_html=raw_html)
        _phase_gated_sections(fc, raw_html=raw_html)
        return

    # JSON response body (json-endpoint-direct-routing): the raw tier now wins on
    # JSON (Verdict.ok), so the body lands here. Synthesize it — trafilatura
    # produces nothing on JSON, and escalating to the jina HTML reader mangles it
    # into a false length_floor. Reuse the JSON-in-script synthesis; an
    # unrecognized shape falls back to the capped JSON text so a valid payload is
    # never lost. Installing pre_rendered_payload skips the gate's content-type
    # guard, exactly like a handler's pre-rendered result.
    if fc.body and is_json_content_type(fc.content_type):
        json_text = fc.body.decode("utf-8", errors="replace")
        json_payload = parse_json_response(json_text)
        if json_payload is not None:
            md = json_to_markdown_rows(json_payload) or json_response_fallback(json_payload.data)
            fc.content_md = md
            fc.pre_rendered_payload = Rendered(content_md=md)
            fc.diagnostics.append(
                Diagnostic(
                    t_ms=extract_dur_start,
                    step="json_response",
                    engine="json_synth",
                    host=None,
                    proxy=None,
                    verdict=Verdict.ok,
                    dur_ms=int((time.perf_counter() - fc.inputs.start_perf) * 1000) - extract_dur_start,
                    extra={"chars": len(md)},
                )
            )
            return
        # Content-type declared JSON but the body did not parse — fall through to
        # normal handling rather than fabricating content.

    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    await a2web_log.info(StageStarted(t_ms=extract_dur_start, step="extract"))
    extract_result = await extract_markdown(raw_html, fc.final_url)
    fc.content_md = extract_result.content_md
    fc.title = extract_result.title
    fc.byline = extract_result.byline
    fc.published = None if extract_result.published and _is_sentinel_date(extract_result.published) else extract_result.published
    fc.headings = extract_result.headings
    fc.links = extract_result.links
    fc.meta_dict = parse_metadata(raw_html)
    await _run_extraction_escalation(fc, raw_html=raw_html)
    _phase_listing_completeness(fc, raw_html=raw_html)
    _phase_gated_sections(fc, raw_html=raw_html)
    extract_dur_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000) - extract_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=extract_dur_start,
            step="extract",
            engine="trafilatura",
            host=None,
            proxy=None,
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        )
    )
    await a2web_log.info(
        StageEnded(
            t_ms=extract_dur_start,
            step="extract",
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        ),
    )
