"""The extraction-escalation ladder — every structured source into the menu (ADR-0005)."""

from __future__ import annotations

import time
from urllib.parse import urljoin

from json_in_html import (
    JsonPayload,
    extract_json_payloads,
    is_answer_bearing,
    rank_payloads,
)
from record_mine import Record, RecordSet, extract_records

from ... import log as a2web_log
from ...events import StageEnded, StageStarted
from ...models import DECLARED_FIELDS_CAP, DeclaredEntity, Verdict
from ...packages.structured_render import declared_subject_entity, json_to_markdown_rows, listing_rows
from ..answer.links import _records_to_next_links
from ..comprehension.menu import _wire_content_md
from ..context import ContentCandidate, FetchContext


async def _run_extraction_escalation(fc: FetchContext, *, raw_html: str) -> None:
    """Collect every structured-extraction source into the menu (ADR-0005).

    No single-winner selection and no value-blind length proxy (retired —
    was: a source replaced `content_md` only when its render was *longer*,
    so a short-but-correct payload silently lost, and a longer *wrong* one
    clobbered the answer-bearing content). Instead: trafilatura prose plus
    every rung that produced output are collected immutably into
    `fc.content_candidates` (fixed order prose → json_synth → record_synth).
    The extractor is fed the whole menu; the wire `content_md` is the
    quality-picked display default (threaded records, else prose, else first
    structured — never the longest). Each rung still self-gates on its own
    preconditions, so a clean article yields only the prose candidate and
    the cascade still falls through to the browser tier.
    """
    candidates: list[ContentCandidate] = []
    if fc.content_md:
        candidates.append(ContentCandidate(source="trafilatura", content_md=fc.content_md))
    json_candidates, json_record_set, json_commerce_rows, declared_entity = await _escalate_via_json(fc, raw_html=raw_html)
    candidates.extend(json_candidates)
    # UNCONDITIONAL, including back to None — deliberately NOT the keep-first
    # rule used for `next_links_handler` below, and the difference matters.
    #
    # That rule protects a PRODUCER's claim from a later stage's reconstruction:
    # the handler knows the site, the miner is guessing. Here there is one
    # producer running twice, over two different bodies. `escalate` re-runs
    # comprehension on whatever the new rung installed, so a keep-first write
    # makes the declaration STICKY: the raw tier's JSON-LD would survive onto a
    # browser body that replaced it, and a2web would relay the publisher's
    # claim about a page it did not serve.
    #
    # A declaration must describe the body the caller actually gets. Losing one
    # because a later rung's body has no JSON-LD is the lesser harm — it costs
    # an index; the alternative costs correctness (ADR-0009: never let the
    # caller mistake one page's facts for another's).
    fc.declared_entity = declared_entity
    record_candidate = await _escalate_via_records(fc, raw_html=raw_html)
    if record_candidate is not None:
        candidates.append(record_candidate)

    fc.content_candidates = candidates
    fc.content_md = _wire_content_md(candidates)
    # The SITE HANDLER's links win. A pre-rendered tier runs this ladder too
    # (see `_phase_extract`), so an unconditional assignment here replaced a
    # handler's site-specific index with the generic miner's — measured on the
    # arXiv listing (bench 2026-08-01): the wire carried `anchor="arXiv:2607.28618"`,
    # a string identical to its own URL, and `reason="discussed page"`, while the
    # handler's paper TITLES and AUTHOR lists were built and discarded.
    #
    # Same rule as the JSON-LD fallback immediately below, and the same rule
    # `_compose_next_links` needed: a later stage may ADD to a producer's index,
    # never silently replace it. The handler knows the site; the miner is
    # guessing from shape.
    if not fc.next_links_handler:
        for cand in candidates:
            if cand.next_links:
                fc.next_links_handler = cand.next_links
                break

    # ADR-0015 — the JSON-LD listing index, as a FALLBACK to the DOM miner.
    # Both `record_set` (the `options` shelf) and `next_links` (`other_pages`)
    # fill only when the structural path produced nothing, so a page that
    # already shipped an index keeps exactly the one it shipped.
    if json_record_set is not None:
        if fc.record_set is None:
            fc.record_set = json_record_set
            fc.record_count = len(json_record_set.records)
            fc.record_commerce_rows = json_commerce_rows
        if not fc.next_links_handler:
            fc.next_links_handler = _records_to_next_links(json_record_set, page_url=fc.final_url or "")


_PROSE_METADATA_LD_TYPES = frozenset({"Article", "NewsArticle"})


def _is_prose_metadata_ld(payload: JsonPayload) -> bool:
    """True when a JSON-LD payload is an Article/NewsArticle metadata echo.

    Such payloads (headline/author/date) merely restate metadata the extracted
    prose already carries, so appending them to above-floor prose on the caller
    wire is redundant bloat — and historically regressed the `blog.html` fixture.
    Product / Organization / ItemList / records are additive and stay eligible.
    Walks `@graph` one level down and tolerates a `@type` that is a str or list.
    """
    data = payload.data
    for entry in data if isinstance(data, list) else [data]:
        if not isinstance(entry, dict):
            continue
        graph = entry.get("@graph")
        for node in graph if isinstance(graph, list) else [entry]:
            if not isinstance(node, dict):
                continue
            raw_type = node.get("@type") or node.get("type")
            types = {raw_type} if isinstance(raw_type, str) else set(raw_type) if isinstance(raw_type, list) else set()
            if types & _PROSE_METADATA_LD_TYPES:
                return True
    return False


async def _escalate_via_json(
    fc: FetchContext, *, raw_html: str
) -> tuple[list[ContentCandidate], RecordSet | None, tuple[dict, ...], DeclaredEntity | None]:
    """Menu source — embedded JSON (incl. JSON-LD).

    Returns one `ContentCandidate` per *renderable* payload, in rank order —
    NOT just the top-ranked one (ADR-0005: collapsing the JSON source to a
    single ranked payload, then `break`, was the same value-blind single-source
    sin one level down; a non-top-ranked payload could hold the answer). No
    length gate. Duplicate renders are suppressed. The display pick takes the
    first (top-ranked) candidate, so the wire `content_md` stays legacy-stable;
    the full set reaches the extractor via the menu. Pure function — emits log
    telemetry, does NOT mutate `fc.content_md`.

    The third element (`type-listing-commerce-fields`) is the normalized row
    dicts behind `json_record_set.records`, position-aligned, empty when
    `json_record_set` is `None`.
    """
    t_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
    await a2web_log.info(StageStarted(t_ms=t_ms, step="json_synth"))
    payloads = extract_json_payloads(raw_html)
    candidates: list[ContentCandidate] = []
    json_record_set: RecordSet | None = None
    json_commerce_rows: tuple[dict, ...] = ()
    seen: set[str] = set()
    # The page's own declaration about its subject. Captured HERE, on the raw
    # HTML, because this is the only place in the pipeline that holds it —
    # `fetcher_response` must never re-derive a fact from the artifact it
    # produced, and re-parsing the body at projection time would be that.
    #
    # Richest-wins across payloads, same rule as within one payload: it is the
    # only tie-break that does not require a2web to hold an opinion about which
    # schema.org type matters more.
    best_declared: tuple[str, dict[str, str]] | None = None
    for payload in rank_payloads(payloads):
        declared = declared_subject_entity(payload)
        if declared is not None and (best_declared is None or len(declared[1]) > len(best_declared[1])):
            best_declared = declared
        rendered = json_to_markdown_rows(payload)
        if rendered and rendered not in seen:
            seen.add(rendered)
            candidates.append(
                ContentCandidate(
                    source="json_synth",
                    content_md=rendered,
                    answer_bearing=is_answer_bearing(payload),
                    is_prose_metadata=_is_prose_metadata_ld(payload),
                )
            )
            # Retain the STRUCTURE behind the render, not just the string.
            # RETURNED rather than written onto `fc`: this escalator is pure by
            # contract (`test_menu_assembly_is_pure`), and the caller is what
            # decides precedence.
            if json_record_set is None:
                built = _rows_to_record_set(listing_rows(payload), base_url=fc.final_url or "")
                if built is not None:
                    json_record_set, json_commerce_rows = built
    dur_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000) - t_ms
    outcome = "no_payloads" if not payloads else ("no_synth" if not candidates else "collected")
    await a2web_log.info(
        StageEnded(
            t_ms=t_ms,
            step="json_synth",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={"outcome": outcome, "payloads": len(candidates)},
        )
    )
    # RETURNED, not written onto `fc` — this escalator is pure by contract
    # (`test_menu_assembly_is_pure`), and the caller decides precedence. Capped
    # here rather than at the wire because the cap is a wire-economics number
    # and `DeclaredEntity` is where it is documented.
    declared_entity: DeclaredEntity | None = None
    if best_declared is not None:
        kind, all_fields = best_declared
        kept = dict(list(all_fields.items())[:DECLARED_FIELDS_CAP])
        declared_entity = DeclaredEntity(
            type=kind,
            fields=kept,
            omitted=len(all_fields) - len(kept),
        )
    return candidates, json_record_set, json_commerce_rows, declared_entity


def _record_detail_text(row: dict, *, title: str) -> str:
    """The free-text `extras` tail for a record's `text`/`detail` — price and
    currency rejoined (D3, `type-listing-commerce-fields`: the JSON-LD source
    dict now carries them as separate scalars, but this free-text rendering
    is a fallback surface, not the typed one, so it stays human-joined)."""
    price = row.get("price")
    extras: list[str] = []
    if price not in (None, ""):
        currency = row.get("currency")
        extras.append(f"{price} {currency}" if currency else str(price))
    rating = row.get("rating")
    if rating not in (None, ""):
        extras.append(str(rating))
    return title if not extras else f"{title} — {' '.join(extras)}"


def _rows_to_record_set(rows: list[dict], *, base_url: str) -> tuple[RecordSet, tuple[dict, ...]] | None:
    """Build a flat `RecordSet` from JSON-LD / framework-state listing rows.

    Converging on `RecordSet` rather than deriving `other_pages` and `options`
    separately is the point: `_records_to_next_links` and `_records_to_options`
    then apply UNCHANGED, so a page reachable by both the JSON-LD path and the
    DOM record-miner yields the same shape of index either way. Deriving each
    field twice is how the two paths would drift.

    Rows without a `url` are kept — they still belong on the `options` shelf
    (they are page content the answer may have skipped); they simply produce no
    onward link. Rows with neither name nor url carry nothing and are dropped.

    `max_depth=0` — a JSON-LD `ItemList` is flat by construction, never a
    threaded discussion, so `is_threaded` is False and the catalog-only
    `_records_to_next_links` path applies.

    Returns the `RecordSet` alongside the surviving rows' own normalized dicts,
    position-aligned 1:1 with `RecordSet.records` (`type-listing-commerce-fields`
    D2) — `record_mine.Record` is shelf-owned and frozen, so typed commerce
    fields (price/currency/rating/stock/seller) can't live on the record
    itself; the caller threads this parallel tuple onto `FetchContext` so
    `_records_to_options` can populate `ListingOption`'s typed fields without
    re-parsing `Record.text`. Built in the same loop as `records` specifically
    so the two can never drift out of alignment.
    """
    records: list[Record] = []
    kept_rows: list[dict] = []
    for row in rows:
        name = row.get("name") or row.get("headline") or row.get("title")
        url = row.get("url")
        if not name and not url:
            continue
        title = " ".join(str(name).split()) if name else str(url)
        link = (title, urljoin(base_url, str(url))) if url else None
        # `detail` mirrors what `_rows_to_md_records` renders, so the option
        # shelf carries the same price/rating signal the markdown shows.
        text = _record_detail_text(row, title=title)
        records.append(
            Record(
                text=text,
                links=(link,) if link else (),
                heading_text=title,
                heading_link=link,
                depth=0,
                markdown=f"- {text}",
            )
        )
        kept_rows.append(row)
    if not records:
        return None
    record_set = RecordSet(records=tuple(records), container="json-ld", child_signature="itemListElement", max_depth=0)
    return record_set, tuple(kept_rows)


async def _escalate_via_records(fc: FetchContext, *, raw_html: str) -> ContentCandidate | None:
    """Menu source — structural record detection.

    Returns a `ContentCandidate` (with `next_links` + the threaded flag)
    whenever the detector produces a record set — no length gate (ADR-0005).
    Pure function — no mutation of `fc.content_md` / `fc.next_links_handler`.
    """
    t_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
    await a2web_log.info(StageStarted(t_ms=t_ms, step="record_synth"))
    record_set = extract_records(raw_html, base_url=fc.final_url or "")
    dur_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000) - t_ms
    if record_set is not None:
        synthetic = record_set.to_markdown()
        if synthetic:
            # Promote the parsed record count (previously logged and discarded)
            # onto fc as the listing-completeness progress metric, and retain the
            # structured record set for the rank-don't-skip option shelf.
            fc.record_count = len(record_set.records)
            fc.record_set = record_set
            next_links = _records_to_next_links(record_set, page_url=fc.final_url or "")
            await a2web_log.info(
                StageEnded(
                    t_ms=t_ms,
                    step="record_synth",
                    verdict=Verdict.ok,
                    dur_ms=dur_ms,
                    extra={
                        "outcome": "collected",
                        "records": len(record_set.records),
                        "threaded": record_set.is_threaded,
                    },
                )
            )
            return ContentCandidate(source="record_synth", content_md=synthetic, next_links=next_links, is_threaded=record_set.is_threaded)
    outcome = "no_records" if record_set is None else "no_synth"
    await a2web_log.info(StageEnded(t_ms=t_ms, step="record_synth", verdict=Verdict.ok, dur_ms=dur_ms, extra={"outcome": outcome}))
    return None
