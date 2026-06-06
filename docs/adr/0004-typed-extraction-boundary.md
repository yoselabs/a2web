# ADR-0004 — Typed extraction boundary

**Status:** Accepted (`record_extract` half, 2026-06-07) · `json-extract` half provisional · **Confirm-by (json-extract):** a future change gated by a captured `json-extract` regression
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

> **Confirmation note (2026-06-07).** The change `typed-extraction-boundary`
> landed the **`record_extract` half** and validated it against the eval
> substrate: the frozen class-C regression `regression/hepsiburada-listing-price`
> flipped from the list price (890, fabricated 1,700, fake 48%) to the correct
> discounted price (700, 21% off) once the value-blind no-separator projection
> in `_own_text` was eliminated. Empirical finding: **node-separation alone was
> sufficient** to flip the judged answer; strikethrough-markup preservation
> helps tag-based sites but does not fire on Hepsiburada (CSS `line-through`,
> not `<del>`), so the CSS-styled-strikethrough case is handed to ADR-0007
> (`real-surface-grounding`). The **`json-extract` half** (typing the schema.org
> subset on the JSON-LD adapter path) remains provisional — same class, a
> different projection site with no captured regression yet — re-pointed to its
> own future instrument-gated change rather than fixed blind.

## Context

The `listing-offer-lift` patch fixed the symptom (lifted `offers.*` for one case) but the lossy-projection *class* still lives in `domain.py` siblings (`_rows_to_md_table` dict-skip for non-commerce rows, `_single_entity_md`'s hardcoded `interesting_keys` allowlist, `_framework_state_to_markdown`'s scalar-only flatten). ADR-0003 bans the value-blind structural-filter projection; this change is the structural elimination.

## Decision (provisional)

Type the **answer-bearing schema.org subset** (`Product`, `Offer`, `ItemList`, `AggregateRating`, `Article`) as boundary types; render *types*, not dicts. The typed adapter is the **only sanctioned path** from structured payload to extractor input; for shapes outside the typed subset, pass the structured payload through (default-keep, drop only known noise) rather than dict-walk-and-filter. Add the pytest-archon fitness function that bans the structural-filter projection pattern (ADR-0003 rule 3).

## Forces / constraints (from agent review — must be satisfied by the change)

- **Package boundary (architecture agent):** boundary types are package-owned (`packages/...`), no `a2web.<domain>` imports; reuse the wobble `Wobbled`-style funnel idiom rather than reinventing a typing discipline.
- **schema.org is unbounded:** type only the valuable subset; the long tail goes through default-keep pass-through, never silent field-projection.
- **No `dict[str, Any]` bag** reintroduced (existing arch rule).

## References

- ADR-0002, ADR-0003; `openspec/changes/archive/2026-06-06-listing-offer-lift/`
- Architecture + semantics agent reviews (2026-06-06)
