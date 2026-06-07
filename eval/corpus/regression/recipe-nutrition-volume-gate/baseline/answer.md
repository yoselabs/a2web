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

### Scope (decided 2026-06-07)

- **Change #3 `multi-source-extraction-input` (ADR-0005)** delivers the menu
  + JSON-rung-emits-all-payloads. It makes the system *robust* to junk
  sources but **cannot** flip this case alone (the Recipe is unrenderable).
  This case is therefore NOT change #3's deterministic gate.
- **Change #4 (ADR-0004 json half)** teaches `json_to_markdown_rows` to
  render `Recipe`/`NutritionInformation`. THEN this case flips: the menu
  carries `268 calories` / `24 grams sugar`, and the judged answer goes
  from "no nutrition, it's a listing" to the correct value. The
  `input_menu_includes: ["268", "kcal"]` RED assertion is added by change #4.

Until then this case documents the unfixed bug (the frozen cassette records
the wrong answer) while passing the deterministic shape gate — the
intended "captured regression awaiting its fix" state.
