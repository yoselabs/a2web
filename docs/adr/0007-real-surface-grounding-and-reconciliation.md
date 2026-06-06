# ADR-0007 — Real-surface grounding and price reconciliation

**Status:** Accepted (provisional) · **Confirm-by:** change `real-surface-grounding`
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

> **Provisional ADR.** Direction agreed 2026-06-06; confirmed/revised when the owning change lands and is validated against the eval substrate. The plan carries a reconfirm task. Sequenced last because it depends on the browser/rendered surface being a first-class input.

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
