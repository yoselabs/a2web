## ADDED Requirements

### Requirement: JSON-LD Recipe synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `Recipe` payload (an entry whose `@type` is `Recipe`, single or within `@graph`) into answer-bearing markdown. It SHALL surface the recipe name (as a heading), `description`, `recipeYield`, the time fields (`prepTime` / `cookTime` / `totalTime`), the `recipeIngredient` list, and — critically — the `nutrition` (`NutritionInformation`) subobject rendered as a readable labelled line carrying its present fields (`calories`, `sugarContent`, `fatContent`, `carbohydrateContent`, `proteinContent`, etc.). Rendering SHALL be content-agnostic (no number/unit special-casing — it renders whichever nutrition fields are present), defensive against shape variance (`nutrition` absent, `recipeInstructions` as `HowToStep[]` vs string, lists vs scalars), and SHALL omit fields it cannot read without raising. A `Recipe` whose `nutrition.calories` is `"268 calories"` SHALL produce output containing `268 calories`.

#### Scenario: Recipe nutrition reaches the synthetic surface

- **WHEN** a page carries a JSON-LD `Recipe` with `nutrition: {@type: NutritionInformation, calories: "268 calories", sugarContent: "24 grams sugar"}`
- **THEN** `json_to_markdown_rows` renders a Recipe block whose text contains `268 calories` and `24 grams sugar`

#### Scenario: Recipe without nutrition still renders

- **WHEN** a `Recipe` payload has no `nutrition` field
- **THEN** the adapter renders the recipe's other answer-bearing fields (name, ingredients, times) and omits the nutrition line, without raising

#### Scenario: Recipe is no longer dropped

- **WHEN** the only answer-bearing JSON-LD payload on a page is a `Recipe`
- **THEN** `json_to_markdown_rows` returns non-empty output (previously a `Recipe` matched no branch and yielded an empty string)

### Requirement: JSON-LD single-entity rendering is default-keep, not an allowlist

Single-entity JSON-LD rendering (`Product` / `Article` / `NewsArticle` / `Recipe` and the like) SHALL render answer-bearing fields by **default-keep**: every key whose value is a scalar or a shallow dict/list of scalars SHALL be surfaced, in the entity's own field order, EXCEPT a fixed **noise denylist** — JSON-LD machinery (`@context`, `@type`, `@id`, `@graph`), image/media URLs (`image`, `thumbnail`, `thumbnailUrl`, `logo`), `mainEntityOfPage`, and values exceeding a length cap (so a full article body is not dumped into a key-value line). The renderer SHALL NOT gate fields against a fixed allowlist of "interesting" keys; an answer-bearing field the author did not anticipate (e.g. a `Product.gtin`, a `Recipe.recipeYield`) SHALL still be surfaced. This eliminates the value-blind structural-filter projection (ADR-0003 / ADR-0004).

#### Scenario: An unanticipated answer-bearing field is surfaced

- **WHEN** a JSON-LD entity carries a scalar field outside any prior fixed allowlist (e.g. `gtin13`, `recipeYield`)
- **THEN** `json_to_markdown_rows` includes that field's key and value in the rendered entity

#### Scenario: Known noise is dropped

- **WHEN** a JSON-LD entity carries `@type`, `@context`, `image`, and a 5,000-character `articleBody`
- **THEN** the rendered entity omits the `@`-prefixed keys, the image URL, and the oversized body, while keeping the entity's short answer-bearing scalars
