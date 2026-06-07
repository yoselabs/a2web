## Why

ADR-0004's `json-extract` half was deferred for want of a captured regression
("don't fix blind"). Change #3 produced it:
`regression/recipe-nutrition-volume-gate` (BBC Good Food banana-loaf). The menu
(ADR-0005) now feeds Haiku every renderable source — but the answer
(`268 calories`, `24 grams sugar`) lives in a `Recipe` JSON-LD payload's
`nutrition` (`NutritionInformation`) object that the JSON renderer **cannot
render**: `domain._ld_json_to_markdown` recognizes `Product` / `Article` /
`ItemList` / `BreadcrumbList`, but a `Recipe` entry yields `""`, so the answer
never reaches the menu regardless of how many sources we collect. The menu is a
delivery mechanism; this change gives it answer-bearing cargo for recipes.

The deeper class is ADR-0004's target: the **value-blind structural-filter
projection**. `_single_entity_md` renders entities through a hardcoded
`interesting_keys` allowlist — any answer-bearing field outside that fixed list
(a Recipe's `nutrition`, `recipeYield`, `totalTime`; a Product's `gtin`,
`material`) is silently dropped. That is the same lossy-projection class
ADR-0003 bans, on the JSON-LD adapter path.

## What Changes

- **Render the `Recipe` type** incl. its `nutrition` (`NutritionInformation`)
  subobject — calories, sugar/fat/carb/protein content, plus yield and times —
  so the answer-bearing fields reach the extractor menu. Flips the captured
  regression.
- **Retire the `interesting_keys` allowlist** in `_single_entity_md` in favor of
  **default-keep**: render all answer-bearing scalar / shallow-nested fields,
  dropping only known noise (`@context`/`@type`/`@id`, image/thumbnail URLs,
  oversized blobs). Per ADR-0004: render the answer-bearing subset, default-keep
  the tail, never value-blind field-projection.
- **Fitness function** (ADR-0003 rule 3): a behavioral guard that an entity
  carrying an *unanticipated* answer-bearing field surfaces it through
  `json_to_markdown_rows` — bans re-introducing a fixed allowlist filter.

## Capabilities

### Modified Capabilities
- `extraction`: the JSON-LD → markdown synthesis adapter (`json_to_markdown_rows`,
  alongside the existing "JSON-LD ItemList synthesis" requirement) renders the
  `Recipe` / `NutritionInformation` answer-bearing subset, and single-entity
  rendering becomes default-keep instead of a fixed `interesting_keys` allowlist.

## Impact

- Code: `src/a2web/domain.py` (`_ld_json_to_markdown`, `_single_entity_md`, new
  `_recipe_md` / nutrition rendering); no boundary-type or signature changes —
  the menu (change #3) is the consumer, unchanged.
- Wire: none. Larger/structured `content_md` only on pages whose JSON the
  display heuristic already selected; the menu (extractor input) gains the
  recipe fields under `debug.content_candidates`.
- Instrument: `regression/recipe-nutrition-volume-gate` is the before/after
  gate — `input_menu_includes: ["268 calories"]` flips green; the judged answer
  flips from "no nutrition, it's a listing" to "268 calories, 24g sugar".
- ADR-0004's `json-extract` half moves from *provisional* to *Accepted*.
