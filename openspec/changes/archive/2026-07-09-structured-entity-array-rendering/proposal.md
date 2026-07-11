## Why

The extraction escalation ladder's single-entity JSON-LD renderer (`domain.py::_single_entity_md`, backing the `extraction` capability's "JSON-LD single-entity rendering is default-keep, not an allowlist" requirement) already surfaces contact facts (`telephone`, `email`, `address`) from `LocalBusiness`/`Organization`/`ContactPoint` schema when they appear as a **single nested object** — this was verified working as designed during a live exploration session (`ask-extraction-token-tuning`). But schema.org explicitly allows `contactPoint` (and similarly `address`, `sameAs`, and other entity-linking properties) to be an **array of objects** — real-world pattern for "sales vs support vs press" contact lines, multiple business locations, etc. `_single_entity_md`'s list-handling branch only keeps scalar list items (`isinstance(v, (str, int, float))`); a list of dicts produces an empty joined string and the whole field is silently dropped. This directly undercuts the requirement's own stated intent — "an answer-bearing field the author did not anticipate... shall still be surfaced" — for exactly the case (multiple contact points) most likely to matter on a real contact page. Per ADR-0009 (never tolerate a silent miss) and the requirement's own default-keep philosophy, a caller asking "what's the support phone number" on a page whose `contactPoint` happens to be an array gets a worse answer than one whose page happens to use a single object — an accident of schema shape, not a real content difference.

## What Changes

- Extend `_single_entity_md`'s list-value branch: when a list contains dict elements (not just scalars), render each dict element as its own flattened sub-line (reusing the existing one-level dict-flatten already used for single nested objects), instead of silently dropping the field when scalars are absent.
- No change to the scalar-list path (e.g. `keywords: ["a", "b", "c"]` keeps rendering as a comma-joined scalar line) — this is additive, not a rewrite of the existing working case.
- No change to `is_answer_bearing` / `_ld_json_strong` (the shelf's `json_in_html` package) — the "is this JSON-LD worth escalating at all" gate is unaffected; this only fixes what happens to a field's value once the entity is already being rendered.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `extraction`: the "JSON-LD single-entity rendering is default-keep, not an allowlist" requirement is extended to explicitly cover list-of-object fields (arrays of `ContactPoint`, `PostalAddress`, or similar), not just list-of-scalar fields.

## Impact

- `src/a2web/domain.py::_single_entity_md` — the list-value branch (currently ~line 304-308).
- Tests: `tests/architecture/test_json_entity_render_is_default_keep.py` (no existing `contactPoint`/array coverage found — genuinely new test surface) plus a fixture-level test under the `extraction` capability's test suite exercising a `LocalBusiness` with an array `contactPoint`.
- No wire/schema change — this only affects what text ends up in the LLM's prompt content (`content_candidates` → the `menu` fed to the extractor), not any response model field or MCP tool signature.
