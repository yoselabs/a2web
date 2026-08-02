"""Candidates in, prompt text and wire content out."""

from __future__ import annotations

from ...packages.block_detector import LENGTH_FLOOR
from ..context import ContentCandidate


def _wire_content_md(candidates: list[ContentCandidate]) -> str:
    """Caller-facing `content_md` — concatenate prose + JSON-LD instead of replacing (task 7.2).

    Narrow, surgical reversal of the 2026-06-07 pick-one decision: the ONLY change
    is the json_synth-wins branch. When above-floor prose coexists with a JSON-LD
    render that would otherwise REPLACE it (json longer than prose — the legacy
    `_pick_display_candidate` rule), surface BOTH, subset-suppressed via the same
    coarse dedup the extractor menu uses. So a product page's specs no longer blind
    the caller to its prose (and vice versa).

    Everything else defers byte-identically to the legacy single-pick:
    - sub-floor / absent prose — the structured answer is what the caller needs;
    - threaded / longer RECORD sets — they RENDER structure prose lost, so they
      genuinely replace (not additive); their contract is untouched;
    - Article/NewsArticle JSON-LD (`is_prose_metadata`) — a metadata echo, never
      concatenated onto prose (the historical blog.html regression).

    The extractor menu is untouched — `assemble_menu` still sees every candidate.
    """
    prose = next((c for c in candidates if c.source == "trafilatura"), None)
    prose_md = prose.content_md if prose is not None else ""
    if prose is None or len(prose_md) < LENGTH_FLOOR:
        return _pick_display_candidate(candidates)
    json_c = next((c for c in candidates if c.source == "json_synth"), None)
    json_would_replace = json_c is not None and len(json_c.content_md) > len(prose_md)
    if json_c is not None and json_would_replace:
        # A metadata echo (Article/NewsArticle) never displaces real above-floor
        # prose: return prose alone — no replace (7.2 intent), no bloat concat.
        if json_c.is_prose_metadata:
            return prose_md
        kept = _suppress_subsets([prose, json_c])
        return "\n\n".join(c.content_md for c in kept if c.content_md)
    return _pick_display_candidate(candidates)


def _pick_display_candidate(candidates: list[ContentCandidate]) -> str:
    """Wire `content_md` default — preserves the pre-ADR-0005 selection.

    The envelope decision (signed off 2026-06-07) is that the DEFAULT wire is
    unchanged: only the extractor's *input* becomes the menu. So this keeps the
    legacy rule byte-for-byte — `json_synth` replaces prose when longer; else a
    record set replaces when threaded OR longer; else prose — so parsers and
    change #2's record-projection wire gate see no change. The full menu still
    reaches Haiku via `assemble_menu`; the retired length proxy lives ONLY here
    now (a display heuristic), no longer gating what the extractor sees.
    """
    prose = next((c for c in candidates if c.source == "trafilatura"), None)
    prose_md = prose.content_md if prose is not None else ""
    # Sub-floor prose is a thin nav/footer fragment. When a strong structured
    # candidate carries the answer, surface it for display — so `fetch_raw`
    # (which returns only `content_md`, not the extractor menu) yields the
    # answer, not the fragment. Above-floor prose keeps the legacy length pick
    # — `answer_bearing` alone is NOT a safe unconditional override here: e.g.
    # `Article`/`NewsArticle` JSON-LD (headline/author/date) is `answer_bearing`
    # by design (see `json_in_html._PREFERRED_LD_TYPES`) yet routinely
    # accompanies genuine, substantial article prose that trafilatura already
    # extracts correctly — swapping it for the metadata stub would be a
    # regression, not a fix (see `answer-bearing-gate-exemption` design notes,
    # 2026-07-09 `make check` finding on the `blog.html` fixture).
    if len(prose_md) < LENGTH_FLOOR:
        answer_c = next((c for c in candidates if c.answer_bearing), None)
        if answer_c is not None:
            return answer_c.content_md
    json_c = next((c for c in candidates if c.source == "json_synth"), None)
    if json_c is not None and len(json_c.content_md) > len(prose_md):
        return json_c.content_md
    rec = next((c for c in candidates if c.source == "record_synth"), None)
    if rec is not None and (rec.is_threaded or len(rec.content_md) > len(prose_md)):
        return rec.content_md
    if prose_md:
        return prose_md
    other = next((c for c in candidates if c.content_md), None)
    return other.content_md if other is not None else ""


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
