# ADR-0007 — Real-surface grounding and price reconciliation

**Status:** Provisional — **held, not built** (investigated 2026-06-08). The targeted class did not reproduce against the substrate; deterministic design kept on the shelf pending a captured regression.
**Date:** 2026-06-06 · **Investigated:** 2026-06-08
**Supersedes:** —
**Superseded by:** —

> **Hold finding (2026-06-08) — the "structured present but wrong" class did not reproduce.**
> Its prerequisite (ADR-0006's rendered-DOM-first-class escalation) was closed
> as unneeded, splitting this ADR into a cheap deterministic half
> (`OperatorHint(price_mismatch)` when structured ≠ visible) and a heavy
> reconciliation half (rendered-DOM grounding). Before building either, a
> captured regression was hunted live:
>
> | Probe | Structured | Visible | Haiku | Verdict |
> |-------|-----------|---------|-------|---------|
> | Hepsiburada search listing | — (record text) | "890 TL %21 700 TL" | 700 | ✅ correct (change #2 node-sep + % cue) |
> | Hepsiburada product detail (Lenovo E310) | JSON-LD `offers.price` = **700** (the *sale*) | 700 | "700.00 TRY; original not shown" (medium) | ✅ correct + honest |
> | Amazon product | — (price is JS-rendered, absent from raw) | absent | "price not present" | ✅ honest, no fabrication |
>
> The class targeted here — structured price *wrong* vs the visible sale
> (list-vs-sale, decoy, stale JSON-LD) — **did not reproduce**: modern commerce
> puts the *correct* sale price in structured data; where the visible surface
> carries a cue, change #2 (node-separation) + change #3 (the menu) let the LLM
> reconcile; where the price is genuinely absent (JS-only), the LLM says so
> honestly. The original price-fidelity bug was the record *projection fusion*,
> already fixed by change #2 — not a structured-vs-visible mismatch.
>
> **Recommendation:** do not build (full reconciliation is overkill given
> changes #2/#3; even the deterministic `price_mismatch` hint lacks a captured
> regression — building it would be fixing blind). Keep the deterministic-hint
> design on the shelf; revisit ONLY if a real stale/wrong-structured-price case
> is captured. The heavy reconciliation half stays unjustified (hallucination +
> token cost per the semantics review; magic budget, ADR-0001).
>
> Side notes from the hunt: (a) Amazon's price is JS-rendered → the ADR-0006
> "present-but-unrendered" gap is broader than first estimated, but a2web's
> honest "not present" keeps it non-harmful (consistent with closing 0006 on
> behavioral grounds); (b) the `ask` tool returns the lean `AskResponse`, which
> does not carry change #3's debug `content_candidates` — only `fetch_raw`
> (`FetchResponse`) exposes the menu. Minor wiring gap, logged for backlog.

## Context

ADR-0002 makes the rendered browser surface canonical truth. Structured data can be *present but wrong* (class C): list price vs sale price, a decoy "from"/accessory price, stale JSON-LD, region/locale-dependent pricing. Trusting structured-only is biased against what the user actually sees.

## Decision (provisional)

Promote the **rendered DOM to a first-class grounding input** (not merely a last-resort escalation tier). With rendered grounding available, the extractor can reconcile metadata-vs-visible values and surface provenance/confidence. Reconciliation is designed *properly* on top of grounding — not as a prompt hack on structured-only input.

## Forces / constraints (from agent review — must be satisfied)

- **Hallucination magnet without grounding (semantics agent):** identifying "the price a user sees" in raw text is unreliable (multiple prices on the page). The **first** step is to *surface* conflicts deterministically via `OperatorHint(code="price_mismatch")` when structured price ≠ extracted price; full LLM reconciliation is gated on actual rendered-DOM grounding, not text guessing.
- **Unbounded scope (semantics agent):** "every structured field has a shadow rendered value that can conflict" is unbounded. Scope to commerce/price first; generalize only with evidence.
- **Dependency:** this change depends on ADR-0006's two-stage escalation / real-surface tier being first-class. Hence last in sequence.
- **Token budget (cost agent):** feeding both structured + rendered text to one call eats Haiku's answer budget; design for it (selective grounding, not whole-DOM dump).

## Backlog-adjacent (explicitly deferred, noted here so they are not lost)

- **WebMCP** — top-of-ladder future surface (the site's own agent API). Owes the same fidelity check as any optimization.
- **Price provenance + locale/currency** — exposing which location/currency produced a price; list-vs-sale provenance.

## References

- ADR-0002 (real surface = truth, fidelity debt); semantics + cost agent reviews (2026-06-06)
- `tiers/browser.py`; `OperatorHint` in `models.py`
