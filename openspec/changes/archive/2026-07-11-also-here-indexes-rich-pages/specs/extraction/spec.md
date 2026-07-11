## MODIFIED Requirements

### Requirement: Router prompt emits also_here in query grammar

The `EXTRACT_ROUTER_V1` system prompt SHALL instruct the model to emit the same-page index (`also_here`) as **queries**, not questions: drop the verb frame and the already-known page entity; keep the target noun(s) plus one discriminating operator (`,` · `vs` · `/`); CAPS at most one load-bearing token; keep a trailing `?` only for DECIDE items; split `and`-joined items. The instruction SHALL direct the model to defer to `options`/`refinement_axes` on a `listing` and never restate a heading, an option row, or a refinement axis (ADR-0015 orthogonality). The instruction SHALL remain in the cacheable `system` bucket (never `cache_prefix`).

The instruction SHALL define "covered" as *relayed everything the page holds on the topic* — NOT merely *answered the asked question*. It SHALL state that a narrow factual ask (one price, one date, one status) on a `product` / `article` / `reference` / `thread` almost never covers the page, and the model SHALL index the unsurfaced sections rather than emitting an empty `also_here`. The key SHALL be omitted only when the page is genuinely thin / single-purpose with nothing left unreturned.

#### Scenario: model emits query-grammar index entries

- **WHEN** `Extractor.extract(..., request_routing=True)` runs and the model produces a same-page index
- **THEN** each entry is a query-grammar string (target + operator, no verb-frame scaffolding), and `and`-joined compounds are split

#### Scenario: narrow ask on a rich page still indexes the withheld sections

- **WHEN** a narrow factual ask (e.g. price / stock) is run against a rich `product` (or `article` / `reference` / `thread`) page whose body carries sections the answer did not surface (specs, description, kit contents)
- **THEN** `also_here` is non-empty and indexes those unsurfaced sections as terse query-grammar entries — the narrow answer does NOT count as having "covered the page"
