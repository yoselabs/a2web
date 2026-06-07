## Context

`domain.json_to_markdown_rows` → `_ld_json_to_markdown` is the JSON-LD →
markdown adapter feeding the extractor menu. It dispatches on `@type`:
`Product`/`Article`/`NewsArticle` → `_single_entity_md`; `ItemList` →
`_render_rows`; `BreadcrumbList` → a breadcrumb line. A `Recipe` entry matches
nothing → `""`.

`_single_entity_md` renders an entity by walking a hardcoded `interesting_keys`
tuple (`name, headline, brand, description, datePublished, author, offers,
aggregateRating, sku, price, priceCurrency, availability`) and emitting only
those. Any answer-bearing field outside the tuple — a `Recipe`'s `nutrition`,
`recipeYield`, `totalTime`; a `Product`'s `gtin`/`material` — is dropped. This
is ADR-0003's banned value-blind structural-filter projection.

The captured regression: BBC `Recipe` payload [2] carries
`nutrition: {@type: NutritionInformation, calories: "268 calories",
sugarContent: "24 grams sugar", fatContent: "13 grams fat", …}`. The fix must
surface it through the adapter.

## Goals / Non-Goals

**Goals:**
- Render the `Recipe` type, incl. its `NutritionInformation` subobject, so the
  answer-bearing fields reach the menu and the regression flips.
- Replace the `interesting_keys` allowlist with **default-keep** entity
  rendering (render answer-bearing fields, drop only known noise).
- Lock the class out with a behavioral fitness function.

**Non-Goals:**
- Formal package-owned pydantic boundary types for the schema.org subset. The
  behavioral class-elimination (default-keep + fitness fn) delivers ADR-0004's
  intent on this path; formalizing typed models in `packages/` is deferred (no
  consumer needs the type today, and the fitness fn enforces the discipline).
- `_rows_to_md_table`'s column-level dict/list skip and
  `_framework_state_to_markdown`'s scalar-only flatten — related siblings of the
  same class, but not on the regression's path; left to a future change with its
  own captured regression (don't fix blind).
- The DOM-`line-through` / CSS-styled rendering (ADR-0007).

## Decisions

### D1 — Render `Recipe` via a typed-shape renderer
`_ld_json_to_markdown` dispatches `@type == "Recipe"` to `_recipe_md(entry)`.
It renders: name (heading), description, `recipeYield`, `prepTime`/`cookTime`/
`totalTime`, `recipeIngredient` (list), and — the answer — the `nutrition`
`NutritionInformation` object as readable `**Nutrition:** calories 268
calories, sugar 24 grams sugar, …` lines. Lists render compactly; absent fields
are omitted. Pure, content-agnostic (no calorie/number special-casing — it
renders the nutrition fields that are present).

### D2 — Entity rendering becomes default-keep, not allowlist
`_single_entity_md` stops iterating a fixed `interesting_keys` tuple. It renders
**every** key whose value is a scalar or a shallow dict/list of scalars, in the
entity's own order, EXCEPT a small **noise denylist**: `@context`/`@type`/`@id`/
`@graph`, `image`/`thumbnail`/`thumbnailUrl`/`logo`/`url` image-CDN values,
`mainEntityOfPage`, and values longer than a cap (e.g. 500 chars, to avoid
dumping a full article body into a key-value line). Nested dicts render as
`k=v, …` (the existing inline form); lists of scalars join with `, `. This is
default-keep: the answer-bearing tail is preserved; only known chrome is
dropped.

### D3 — `NutritionInformation` is the worked example of D2
The `nutrition` subobject is just a nested dict under default-keep, but recipes
are common enough to render it explicitly (D1) as a labelled `Nutrition` line
so the numbers are adjacent and citable, rather than a generic `nutrition={…}`
blob. Both surface `268 calories`; D1 is the readable form.

### D4 — Proof: assert the menu (ADR-0005 D7), then the judged flip
The deterministic gate adds `input_menu_includes: ["268 calories"]` to
`regression/recipe-nutrition-volume-gate/baseline/contract.json` — RED today
(Recipe renders `""`), GREEN after D1. The judged-answer flip is validated with
a live LLM on the frozen bytes (as in changes #2/#3) and the cassette
re-recorded.

## Risks / Trade-offs

- **Default-keep bloats entity output / changes existing Product·Article
  renders** — the central risk. Mitigated by the noise denylist + value-length
  cap, and by re-running the `json_extract` capability tests; any intended
  output change is re-blessed, any regression is fixed. Net: more answer-bearing
  fields surface (the point), bounded by the denylist.
- **Token cost** — recipes/entities render a few more fields into the menu.
  Bounded (one entity, capped values); the menu's priority-trim (change #3)
  still applies. Measured if it matters.
- **`Recipe` shape variance** (`nutrition` as dict vs list; `recipeInstructions`
  as `HowToStep[]` vs string) — `_recipe_md` defends each field defensively and
  omits what it can't read, never raising.
