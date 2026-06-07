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

### Mechanism — the volume gate clobbers the answer-bearing content

This is the ADR-0005 class: **mutually-exclusive single-source selection
gated by a value-blind length proxy**. On this page:

1. `trafilatura` extracts the real recipe prose (ingredients, nutrition,
   method) — `fc.headings` still proves it: `Ingredients`, `Nutrition`,
   `Method`, `step 1–7`, FAQ.
2. `_escalate_via_records` **false-fires on the sidebar widgets** (Almond
   butter / Plum & raspberry jam / Cappuccino / app promo / subscription /
   podcast), rendering them as a 6-record "Listing".
3. The volume gate (`fetcher.py:1133`, `len(synthetic) > original_len`)
   lets that longer sidebar render **replace** the real recipe content.
4. The extractor only ever sees the sidebar junk → answers that the page
   has no nutrition and is "a listing".

Two independent defects compound: the record detector's sidebar
false-positive (a real-surface precision issue), and the volume gate's
single-source replacement (the ADR-0005 class). The **menu** fix
(ADR-0005 — feed prose + JSON-LD + records *together*, let the LLM choose)
makes the system robust to the first by curing the second: even when a
junk source is detected, the answer-bearing sources survive in the input
and the LLM picks `268 kcal`.

### Expected flip after change #3 (`multi-source-extraction-input`)

The extractor input includes the Recipe / NutritionInformation payload
(and/or the DOM nutrition prose) → the judged answer flips from
"no nutrition, it's a listing" to "268 kcal, 34g sugar". The precise
deterministic projection assertion is pinned by that change's tasks,
alongside the wire-envelope decision (which candidate `content_md`
surfaces).
