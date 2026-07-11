## ADDED Requirements

### Requirement: Router prompt emits follow-ups in query grammar

The `EXTRACT_ROUTER_V1` system prompt SHALL instruct the model to emit the same-URL follow-up list (`refine`) as **queries**, not questions. The instruction SHALL direct the model to: drop the verb frame and the already-known page entity; keep the target noun(s) plus one discriminating operator (`,` list · `vs` contrast · `/` alternatives); CAPS at most one load-bearing token when a qualifier or differentiator decides the answer; keep a trailing `?` only for judge/determine-which (DECIDE) items; and split any `and`-joined follow-up into two items. The follow-up instruction SHALL remain in the cacheable `system` bucket (never `cache_prefix`), consistent with the router template's cache discipline.

#### Scenario: model emits query-grammar follow-ups

- **WHEN** `Extractor.extract(..., request_routing=True)` runs against a page and the model produces follow-ups
- **THEN** each follow-up in the routing payload is a query-grammar string (target + operator, no verb-frame scaffolding), and `and`-joined compounds are split into separate items

#### Scenario: follow-up instruction is cacheable

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y1)` and `render(content=X, ask=Y2)` are compared
- **THEN** the query-grammar follow-up instruction text is byte-identical across both (it lives in `system`, not `tail` or `cache_prefix`)
