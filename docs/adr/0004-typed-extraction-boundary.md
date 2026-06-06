# ADR-0004 — Typed extraction boundary

**Status:** Accepted (provisional) · **Confirm-by:** change `typed-extraction-boundary`
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

> **Provisional ADR.** This records the *direction* agreed in the 2026-06-06 explore session. It is confirmed, revised, or superseded when its owning change lands and is validated against the eval substrate (ADR-0002). The change's `tasks.md` carries an explicit "reconfirm/update this ADR" task. Do not treat it as settled until then.

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
