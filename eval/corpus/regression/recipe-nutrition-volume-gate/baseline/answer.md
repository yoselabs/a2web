# recipe-nutrition-volume-gate — reference answer

**Correct answer (what a faithful pipeline should produce):**

> One serving contains **268 kcal** with **34g sugar** (per the recipe's
> nutrition panel / `NutritionInformation` JSON-LD).

The page *is* the "Brilliant banana loaf" recipe. The answer lives in the
page bytes in **three** places: the rendered DOM nutrition list
(`nutrition-list__label">kcal</span>268`), 3× `Recipe` JSON-LD, and 3×
`NutritionInformation` JSON-LD.

## The bug (failure class C — captured 2026-06-07)

The frozen LLM answer below is **wrong**:

> "The page does not contain nutritional information. It is a recipe
> listing/homepage … To find calorie and sugar content, you must click
> into individual recipe pages."

### Mechanism — a COMPOUND failure (instrument finding, 2026-06-07)

Building the eval substrate before fixing earned this: the case needs
**two** fixes, and the menu (ADR-0005) alone does **not** flip it. The
answer (`268 calories`, `24 grams sugar`) lives in `Recipe` JSON-LD
payload [2] (`nutrition: {@type: NutritionInformation, calories:
"268 calories", sugarContent: "24 grams sugar", …}`) — but no extraction
rung surfaces it:

1. `trafilatura` mis-selects the **sidebar** (Almond butter / Plum &
   raspberry jam / Cappuccino / promos) as the main content — a
   content-selection miss. The recipe prose (and its nutrition) is dropped.
   `fc.headings` still parses `Ingredients`/`Nutrition`/`Method`, proving
   the real structure was seen.
2. `_escalate_via_json` renders only the **top-ranked** payload (the
   sidebar `ItemList`) then `break`s — the `Recipe` payload [2] is never
   reached. *The same value-blind single-source sin, one level down inside
   the JSON rung.* → ADR-0005 (change #3: emit ALL renderable payloads).
3. `json_to_markdown_rows(Recipe)` returns `""` — it only knows `ItemList`,
   so even reaching payload [2] yields nothing. → ADR-0004 json half
   (render the answer-bearing schema.org subset incl. `NutritionInformation`).
4. `_escalate_via_records` false-fires on the sidebar again.

So the extractor menu carries three flavors of "sidebar" and never `268`.

### Resolution (two changes, 2026-06-07)

- **Change #3 `multi-source-extraction-input` (ADR-0005)** delivered the menu
  + JSON-rung-emits-all-payloads. Necessary but not sufficient here: the
  `Recipe` payload was still unrenderable, so `268` did not reach the menu.
- **Change #4 `answer-bearing-json-rendering` (ADR-0004 json half)** taught
  `json_to_markdown_rows` to render `Recipe`/`NutritionInformation` (and made
  single-entity rendering default-keep instead of an allowlist). **This case is
  now FIXED:** the menu carries `268 calories` / `24 grams sugar`
  (`input_menu_includes: ["268 calories"]` green), and a live LLM on these
  frozen bytes flipped the judged answer to:

  > "Per serving (assuming 8-10 slices): **268 calories** and **24 grams
  > sugar**. The recipe yields 8-10 slices total."

  The cassette (`inputs/llm/extract.json`) was re-recorded to this correct
  answer, replacing the captured "no nutrition, it's a listing" bug. The
  deterministic menu assertion is the standing offline gate.
