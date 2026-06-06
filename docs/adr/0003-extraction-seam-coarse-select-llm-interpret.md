# ADR-0003 — The extraction seam: deterministic coarse-select, LLM interprets

**Status:** Accepted
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

## Context

The `listing-offer-lift` bug (ADR-0002) put a **fine-grained field-selection decision** — "which fields of a `Product` survive into the content the LLM reads" — inside deterministic code (`_rows_to_md_table`'s dict-walk). Field selection is a *judgment task*; doing it with a value-blind structural heuristic silently dropped the answer-bearing fields.

During the same explore session, the architecture-axis agent showed the proposed "menu" fix (feed the LLM multiple structured payloads, deduped) reintroduces the *same* class: a cross-source dedup needs to know "which fields make two products the same entity" — which is field-interpretation creeping back into deterministic code. The principle (ADR-0002, rule 5) predicted this.

## Decision

Draw the **extraction seam** explicitly and make it normative:

```
  DETERMINISTIC  (cheap, reproducible, COARSE, lossless-biased)
    • locate answer-bearing payload(s) (which JSON-LD block / which array)
    • rank + coarse subset-suppress (drop a payload whose entities ⊆ a higher-ranked one)
    • trim to token budget; strip blob noise (image CDNs, scripts)
    • cheap answerability PRE-probe (commerce intent + zero price token → descend before spending the LLM)
  ═══════════════════════════════ SEAM ═══════════════════════════════
  LLM  (fine-grained INTERPRETATION — where judgment lives)
    • pick fields · dedup by semantic identity · reconcile metadata-vs-rendered
    • judge answerability · assign confidence/provenance
```

Normative rules:

1. **Deterministic code may do coarse, lossless-biased SELECTION and TRIMMING only.** It may rank, suppress strict subsets, and cut to a token budget. It may **not** project a subset of fields out of an entity, nor decide semantic equality of entities.
2. **Fine-grained field interpretation lives on the LLM side** (or in a typed contract — ADR-0004 — where the field set is enumerated, not heuristically filtered).
3. **The value-blind structural-filter projection pattern is banned.** A function that walks an untyped `dict | list` and includes/excludes fields by `isinstance(v, (dict, list))` / `startswith("@")` / a hardcoded "interesting keys" allowlist is forbidden in the extraction path. An arch fitness function (pytest-archon, per ADR-0001 Pattern 3) enforces this; the typed adapter (ADR-0004) is the only sanctioned path, with the fitness function as the backstop against a parallel dict-walker reappearing.

## Consequences

**Positive**

- The lossy-projection class becomes structurally unwritable in the extraction path (the typed adapter is the only route; the fitness function trips on any reintroduction).
- The seam tells every future contributor where a new decision belongs: "is this coarse selection or field interpretation?" answers "deterministic or LLM."

**Negative / accepted cost**

- Moving field interpretation to the LLM shifts tokens onto the model (more context in, the menu — ADR-0005). The cost is real and is *measured* against the eval substrate, not assumed acceptable.
- Coarse subset-suppression is a weaker dedup than semantic atomization; the same entity in two non-subset shapes may still reach the LLM twice. Full cross-source atomization is backlog; coarse suppression is the seam-respecting floor.

## Implementation

- ADR-0004 (typed extraction boundary) implements rule 1–2 for the answer-bearing schema.org subset and adds the arch fitness function for rule 3.
- ADR-0005 (multi-source input) implements the coarse select/suppress/trim and the LLM-side dedup.

## References

- ADR-0001 — Structural prevention over vigilance (Pattern 1 typed funnel, Pattern 3 fitness functions)
- ADR-0002 — Real surface is ground truth (rule 5: optimizations distil, not interpret)
- Architecture-axis agent review (this conversation, 2026-06-06) — the dedup-as-leak finding
