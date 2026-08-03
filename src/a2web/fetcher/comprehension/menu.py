"""Candidates in, prompt text and wire content out."""

from __future__ import annotations

from ...packages.block_detector import LENGTH_FLOOR
from ..context import ContentCandidate


def _wire_content_md(candidates: list[ContentCandidate]) -> str:
    """Caller-facing `content_md`. **Relative length no longer selects anything.**

    Decided 2026-08-02, resolving a three-way contradiction in which the two
    specs and the shipped code each stated a different rule:

    - `extraction` said pick by KIND and that "rendered length SHALL NOT be the
      selector";
    - `content-expectations` said prose and JSON-LD concatenate, never replace;
    - this function said *the longer one wins*, which is neither.

    The resolution is concatenate-with-carve-outs, and the reason is the
    asymmetry this project applies everywhere else: **dropping a candidate is a
    SILENT loss.** `fetch_raw` returns `content_md` and nothing else, so a caller
    handed the prose cannot tell that a price, a phone number or a rating was
    extracted and then discarded — and recovering it costs a whole new proxy
    fetch. Extra text costs tokens, which are cheap and visible. Length cannot
    know which candidate carries the answer: a 200-char JSON-LD block holding the
    price lost to 800 chars of boilerplate, and inverting the character counts
    inverted the verdict, which is the definition of a rule that is not about
    the content.

    Three cases, none of them a comparison:

    1. **A record set exists → it wins outright.** The record detector's guards
       reject articles, so a record set at all means the page IS a listing: the
       rendered rows are the content and the prose is nav or a blurb. Gluing is
       wrong here specifically because trafilatura often extracts the row text
       too, so the caller would receive the same rows twice.
    2. **Prose is absent or sub-floor → the structured candidate wins.** A thin
       nav/footer fragment is not an article; an `answer_bearing` payload is
       preferred, else any JSON-LD render.
    3. **Real prose → prose + JSON-LD, subset-suppressed.** Except an
       `Article`/`NewsArticle` metadata echo (`is_prose_metadata`), which is
       headline + author + date and adds nothing to an article it is describing.
       Stapling it on was a measured regression (`blog.html`, 2026-07-09), so it
       stays a carve-out.

    `LENGTH_FLOOR` survives and is not a contradiction of the above: it answers
    "is this prose at all", a property of one candidate. What was removed is
    `len(a) > len(b)`, which claimed to answer "which candidate is better" — a
    question character counts cannot see.

    The extractor menu is untouched — `assemble_menu` still sees every candidate.
    """
    prose = next((c for c in candidates if c.source == "trafilatura"), None)
    prose_md = prose.content_md if prose is not None else ""

    records = next((c for c in candidates if c.source == "record_synth"), None)
    if records is not None and records.content_md:
        return records.content_md

    json_c = next((c for c in candidates if c.source == "json_synth"), None)

    if prose is None or len(prose_md) < LENGTH_FLOOR:
        answer_c = next((c for c in candidates if c.answer_bearing), None)
        if answer_c is not None and answer_c.content_md:
            return answer_c.content_md
        # EVERY json candidate, not `next(...)`. `_escalate_via_json` returns
        # one per renderable payload in rank order and this took the first,
        # discarding the rest — the same value-blind single-source pick this
        # module's docstring rejects, surviving one level down.
        #
        # It was masked until 2026-08-03 by `_ENTITY_TYPES`: a page's chrome
        # `WebSite` / `Organization` payload rendered as "" and so never became
        # a candidate at all, leaving the content payload first by accident.
        # Deleting that gate (ADR-0018) made chrome renderable and it began
        # winning the pick outright — Yandex Market's `WebSite: Yandex Market`
        # displaced the product rows. Removing a filter revealed a selection
        # bug rather than causing one, and reinstating the filter to hide it
        # would be treating the symptom.
        #
        # Concatenating is the same trade the prose branch below already makes:
        # extra text costs visible tokens, a dropped payload costs a whole new
        # proxy fetch to recover. Duplicate renders are already suppressed
        # upstream by `seen`, and subsets are suppressed here.
        json_all = [c for c in candidates if c.source == "json_synth" and c.content_md]
        if json_all:
            kept = _suppress_subsets(json_all)
            return "\n\n".join(c.content_md for c in kept if c.content_md)
        if prose_md:
            return prose_md
        other = next((c for c in candidates if c.content_md), None)
        return other.content_md if other is not None else ""

    if json_c is not None and json_c.content_md and not json_c.is_prose_metadata:
        kept = _suppress_subsets([prose, json_c])
        return "\n\n".join(c.content_md for c in kept if c.content_md)
    return prose_md


# Static, content-free section labels. Byte-stable so the assembled menu —
# which IS the extractor's prompt-cache prefix (`cache_prefix = {content}`) —
# is identical across different asks on one fetched page (ADR-0005 D2).
_MENU_LABELS: dict[str, str] = {
    "trafilatura": "## source: prose",
    "json_synth": "## source: structured (json)",
    "record_synth": "## source: structured (records)",
}


def assemble_menu(candidates: list[ContentCandidate]) -> str:
    """Assemble the multi-source extractor input - the menu (ADR-0005 D1-D4).

    Pure function of the candidate list: coarse subset-suppression (drop a
    candidate whose normalized text is a strict substring of another's, and
    exact duplicates), then deterministic concatenation with static labels in
    priority order (prose, json, records). Records render last, so the
    extractor's downstream tail-truncation cap drops the lowest-priority
    source first (D3) — no separate cap pass here, keeping the menu byte-stable
    across asks (D2). No timestamps / counts / identity / dict-order.
    """
    blocks: list[str] = []
    for cand in _suppress_subsets(candidates):
        if not cand.content_md:
            continue
        label = _MENU_LABELS.get(cand.source, f"## source: {cand.source}")
        blocks.append(f"{label}\n\n{cand.content_md}")
    return "\n\n".join(blocks)


def _normalize_ws(text: str) -> str:
    """Whitespace-collapsed form for robust substring comparison."""
    return " ".join(text.split())


def _suppress_subsets(candidates: list[ContentCandidate]) -> list[ContentCandidate]:
    """Drop candidates that are a strict substring (or exact dup) of another.

    Guards the 3-7x duplication when the same payload appears across
    microdata / og / ld_json / records. Coarse only - semantic dedup is the
    LLM's job (ADR-0003). Pure + order-preserving.
    """
    texts = [_normalize_ws(c.content_md) for c in candidates]
    kept: list[ContentCandidate] = []
    seen: set[str] = set()
    for i, (norm, cand) in enumerate(zip(texts, candidates, strict=True)):
        if not norm or norm in seen:
            continue
        if any(j != i and norm != texts[j] and norm in texts[j] for j in range(len(texts))):
            continue
        kept.append(cand)
        seen.add(norm)
    return kept
