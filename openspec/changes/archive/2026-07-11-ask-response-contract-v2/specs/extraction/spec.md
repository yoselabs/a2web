## ADDED Requirements

### Requirement: Router prompt emits also_here in query grammar

The `EXTRACT_ROUTER_V1` system prompt SHALL instruct the model to emit the same-page index (`also_here`) as **queries**, not questions: drop the verb frame and the already-known page entity; keep the target noun(s) plus one discriminating operator (`,` · `vs` · `/`); CAPS at most one load-bearing token; keep a trailing `?` only for DECIDE items; split `and`-joined items. The instruction SHALL direct the model to defer to `options`/`refinement_axes` on a `listing` and never restate a heading, an option row, or a refinement axis (ADR-0015 orthogonality). The instruction SHALL remain in the cacheable `system` bucket (never `cache_prefix`).

#### Scenario: model emits query-grammar index entries

- **WHEN** `Extractor.extract(..., request_routing=True)` runs and the model produces a same-page index
- **THEN** each entry is a query-grammar string (target + operator, no verb-frame scaffolding), and `and`-joined compounds are split

### Requirement: Router prompt emits a unified other_pages shape

The `EXTRACT_ROUTER_V1` system prompt SHALL instruct the model to emit off-page pointers as a single `other_pages` list with a per-item `kind` (`structural` | `drilldown`), replacing the separate `try_url` / `next_links` instructions. It SHALL preserve the ADR-0014 grounding rules: URLs are closed-set `{{n}}` handles or literally on the page; the "LINKS IN THE ANSWER · HARD RULE" clause stays; drilldown `reason`s are question-conditioned; the `{{{{n}}}}` double-brace marker discipline is retained so `.format()` emits the literal `{{n}}`.

#### Scenario: unified links instruction preserves grounding

- **WHEN** the model emits off-page pointers under `request_routing=True`
- **THEN** they appear as `other_pages` entries with `kind`, each `url` is a rehydratable `{{n}}` handle or on-page literal, and off-domain targets are flagged
