# ADR-0005 — Multi-source extraction input (the "menu")

**Status:** Accepted · **Confirmed-by:** change `multi-source-extraction-input` (landed 2026-06-07)
**Date:** 2026-06-06 · **Confirmed:** 2026-06-07
**Supersedes:** —
**Superseded by:** —

> **Confirmed 2026-06-07.** The menu landed: the extractor is fed prose +
> every renderable JSON payload + records (`assemble_menu`), the value-blind
> length proxy is retired from the input path, and the default wire stays
> byte-identical (the proxy survives only as the `content_md` display
> heuristic). Proven deterministically by the menu unit tests
> (`tests/capabilities/extraction/test_menu_assembly.py`) and the arch fitness
> function (`tests/architecture/test_menu_assembly_is_pure.py`).
>
> **Two findings from the instrument (it caught a blind fix):**
> 1. The JSON rung was *itself* single-source — it rendered only the
>    top-ranked payload then `break`ed, so a non-top-ranked payload (e.g. a
>    `Recipe` among `ItemList`s) was lost. Fixed here: emit ALL renderable
>    payloads. This is the same value-blind single-source class, one level down.
> 2. The motivating `regression/recipe-nutrition-volume-gate` case is NOT
>    menu-fixable alone: `json_to_markdown_rows` cannot render
>    `Recipe`/`NutritionInformation` (returns `""`), so `268` never reaches the
>    menu regardless. That is a *rendering-coverage* gap, not a *selection* gap
>    — it belongs to ADR-0004's json half and is routed to **change #4**, where
>    the recipe case becomes the captured regression that confirms it.
>
> Remaining (does not block this ADR): a live menu-only corpus regression
> (task 6.2) as substrate enrichment beyond the deterministic proof.

## Context

Today the extraction ladder picks **one** structured payload, renders it, and **replaces** `content_md` only if longer (the volume proxy, `fetcher.py:1102`). ADR-0002 bans volume-as-fidelity; ADR-0003 moves field interpretation to the LLM. The "menu" feeds the LLM prose + the selected structured payload(s) and lets it choose.

## Decision (provisional)

Feed the extractor **both** trafilatura prose and the coarsely-selected structured payload(s) instead of a single replace-or-not. Retire the volume-gate replace rule — but **document its rationale first** (it was a quality-aware guard: threaded records always replace, flat records/JSON replace only when longer, to avoid clobbering good prose). Start generous (more context to the LLM); optimize token cost down later, measured.

## Forces / constraints (from agent review — must be satisfied)

- **Cache-prefix discipline (cost agent):** `EXTRACT_CACHEABLE_V1` / `EXTRACT_ROUTER_V1` cache-prefix byte-equality must survive multi-source input, or the Anthropic prompt-cache hit-rate regresses (est. material $ at volume). Per-page-structure variation must not leak into the cache prefix.
- **Budget (cost agent):** respect `max_content_chars`; budget-aware trim with a *priority* (don't truncate prose and synth equally-blindly).
- **Dedup is the LLM's job (architecture agent):** deterministic side does only coarse subset-suppression (ADR-0003); semantic dedup is interpretation. Guard against 3–7× duplication (same ItemList in microdata + og + ld_json + window).
- **Content-state model (architecture agent):** the menu likely needs an immutable `fc.content_candidates: list[ContentCandidate]` rather than mutating the single `fc.content_md` slot; define which candidate the wire serializer surfaces.

## References

- ADR-0002, ADR-0003; cost + architecture agent reviews (2026-06-06)
- `fetcher.py:1075-1115` (current `_escalate_via_json` + volume gate to be documented & retired)
