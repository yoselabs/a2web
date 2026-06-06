# ADR-0005 — Multi-source extraction input (the "menu")

**Status:** Accepted (provisional) · **Confirm-by:** change `multi-source-extraction-input`
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

> **Provisional ADR.** Direction agreed 2026-06-06; confirmed/revised when the owning change lands and is validated against the eval substrate. The plan carries a reconfirm task. The cost trade-offs below are the specific things the substrate must measure before this is confirmed.

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
