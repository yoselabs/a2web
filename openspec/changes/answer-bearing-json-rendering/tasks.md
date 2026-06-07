## 1. Red — prove the gap (BDD-first)

- [x] 1.1 Add `input_menu_includes: ["268 calories"]` to `regression/recipe-nutrition-volume-gate/baseline/contract.json`. Confirm the regression replay FAILS red — the `Recipe` payload renders `""` today, so `268 calories` is absent from the menu.
- [x] 1.2 Add a focused unit test (`tests/capabilities/extraction/test_json_recipe_synthesis.py`): `json_to_markdown_rows` over a minimal `Recipe` payload with `nutrition.calories="268 calories"` + `sugarContent` → output contains `268 calories` and `24 grams sugar`. Confirm red.
- [x] 1.3 Add a unit test for default-keep: a `Product` entity carrying a scalar field outside the old `interesting_keys` tuple (e.g. `gtin13`) → the field is surfaced. Confirm red.

## 2. Render the Recipe type

- [x] 2.1 `_ld_json_to_markdown`: dispatch `@type == "Recipe"` to a new `_recipe_md(entry)`.
- [x] 2.2 `_recipe_md`: render name (heading), `description`, `recipeYield`, `prepTime`/`cookTime`/`totalTime`, `recipeIngredient` (list), and the `nutrition` `NutritionInformation` object as a labelled line of present fields. Defensive against shape variance; omit unreadable fields; never raise. Make 1.2 green.

## 3. Default-keep entity rendering

- [x] 3.1 `_single_entity_md`: drop the hardcoded `interesting_keys` tuple. Render every scalar / shallow dict-or-list-of-scalars field in entity order, minus the noise denylist (`@`-keys, `image`/`thumbnail`/`thumbnailUrl`/`logo`, `mainEntityOfPage`, values over the length cap). Keep the existing nested-dict inline `k=v` form and list join. Make 1.3 green.
- [x] 3.2 Re-run the `json_extract` + `extraction` capability tests; re-bless any intended Product/Article output changes, fix any genuine regression.

## 4. Fitness function (ADR-0003 rule 3)

- [x] 4.1 Add `tests/architecture/test_json_entity_render_is_default_keep.py`: a behavioral guard that an entity field outside any fixed allowlist is surfaced by `json_to_markdown_rows` (bans re-introducing an allowlist filter). Include the acceptance-check docstring (re-add an allowlist, confirm red, revert).

## 5. Prove the fidelity fix end-to-end (eval substrate)

- [x] 5.1 Run `make eval-replay CORPUS=regression` — `input_menu_includes: ["268 calories"]` (1.1) now passes green; the answer-bearing Recipe nutrition reaches the menu.
- [x] 5.2 Validate the judged-answer flip with a live LLM against the **frozen bytes** (as in changes #2/#3): fixed pipeline + live Haiku answers "268 calories, 24 grams sugar" (correct) vs the captured "no nutrition, it's a listing" (wrong). Re-record `inputs/llm/extract.json`; update `baseline/answer.md` before/after.

## 6. Wrap

- [x] 6.1 ADR-0004: move the `json-extract` half from *provisional* to *Accepted*; record the worked regression. Update `docs/architecture/extraction-fidelity-program.md` Status (change #4 landed; recipe regression flipped).
- [x] 6.2 Update `CHANGELOG.md` (Fixed — JSON-LD Recipe/NutritionInformation rendering + default-keep entity projection).
- [x] 6.3 `make check` green (lint + ty + test-cov + arch).
- [x] 6.4 `openspec validate answer-bearing-json-rendering`.
