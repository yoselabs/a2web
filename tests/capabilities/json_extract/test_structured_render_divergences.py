"""The three divergences resolved when the renderer moved to `packages/`.

`domain.py` held 381 lines of structured-data rendering that read no settings
and imported nothing from a2web. Three accidental divergences inside it were the
evidence that nobody maintained it as one thing, and each is fixed here rather
than carried across the package boundary — a duplicate that survives a move is a
duplicate the move endorsed.

Each test names the loss it prevents, because "there were two table renderers"
is not by itself a defect; what makes it one is that a fix to either missed the
other, and both were wrong in different places.
"""

from __future__ import annotations

from a2web.packages.structured_render import (
    _ENTITY_VALUE_CAP,
    _TABLE_CELL_CAP,
    _TABLE_ROWS_CAP,
    _opengraph_to_markdown,
    _rows_to_md_table,
    _single_entity_md,
)

# --------------------------------------------------------------------- #
# Divergence one — two table renderers
# --------------------------------------------------------------------- #


def test_table_columns_are_the_union_of_every_row_not_a_sample() -> None:
    """THE regression, and the one that cost real data.

    Columns were inferred from `rows[:5]`. Rows here are heterogeneous BY
    CONSTRUCTION — `_normalize_commerce_row` promotes `price`/`url`/`rating`
    only where the source carries them — so a key absent from the first five
    rows was deleted from the table for every row that had it.

    Identical to the `wire.encode_rows` defect fixed on 2026-07-31, in the other
    renderer. A sample cannot describe rows that differ.
    """
    rows = [{"name": f"item {i}"} for i in range(6)]
    rows.append({"name": "item 6", "price": "99 USD"})

    table = _rows_to_md_table(rows, title="T")

    assert "price" in table, "a column present only past the sample window was deleted"
    assert "99 USD" in table


def test_the_opengraph_renderer_is_the_table_renderer() -> None:
    """There is one table renderer, and OpenGraph feeds it.

    The hand-rolled copy had the same escaping and header shape but a different
    cell cap and row cap, which is how the column-sampling bug could live in one
    and not the other — so neither was ever wholly right.
    """
    table = _opengraph_to_markdown({"og:title": "Hello", "og:type": "article"})
    assert table.startswith("### OpenGraph")
    assert "| property | value |" in table
    assert "| og:title | Hello |" in table


def test_the_cell_cap_is_the_wider_of_the_two() -> None:
    """200, not 80 — the truncated cells are descriptions and titles.

    Cutting one at 80 characters drops answer-bearing prose the caller cannot
    recover without another fetch, which is the loss the wider cap prevents.
    """
    long_value = "x" * 400
    table = _rows_to_md_table([{"name": long_value}], title="T")
    assert "x" * _TABLE_CELL_CAP in table
    assert "x" * (_TABLE_CELL_CAP + 1) not in table


def test_an_over_cap_table_declares_its_truncation() -> None:
    """The table renderer had NO row cap, so a 900-row table went to the LLM whole.

    Capping it silently would be the other failure — the handlers were brought
    off exactly that on 2026-08-01 — so the cap declares.
    """
    rows = [{"name": f"item {i}"} for i in range(_TABLE_ROWS_CAP * 2)]
    table = _rows_to_md_table(rows, title="T")

    assert table.count("| item ") == _TABLE_ROWS_CAP
    assert f"{_TABLE_ROWS_CAP} of {_TABLE_ROWS_CAP * 2} rows" in table
    assert "partial view" in table


def test_a_table_within_the_row_cap_stays_silent() -> None:
    """Anti-vacuity: a note on every table is a note on none of them."""
    table = _rows_to_md_table([{"name": "only"}], title="T")
    assert "partial view" not in table


# --------------------------------------------------------------------- #
# Divergence two — the Recipe allowlist
# --------------------------------------------------------------------- #

_RECIPE = {
    "@type": "Recipe",
    "name": "Banana bread",
    "recipeYield": "8 slices",
    "recipeIngredient": ["140g butter", "2 large eggs"],
    "recipeInstructions": "Cream the butter and sugar, fold in the flour, bake for 50 minutes.",
    "recipeCuisine": "British",
    "recipeCategory": "Dessert",
}


def test_a_recipes_instructions_reach_the_caller() -> None:
    """THE regression, and the sharpest one in this file.

    `_recipe_md` rendered a fixed key list: name, description, yield, the three
    times, ingredients, nutrition. `recipeInstructions` — the STEPS, the single
    most answer-bearing field on a recipe page — was not in it, so a2web served
    a recipe's ingredients and silently dropped how to cook them. So were
    `recipeCuisine`, `recipeCategory`, `aggregateRating` and `keywords`.

    `_single_entity_md`'s own docstring argues that an allowlist "silently loses
    an unanticipated answer-bearing field" (ADR-0004 default-keep). It was right,
    and `_recipe_md` was the counterexample thirty lines above it.
    """
    rendered = _single_entity_md(_RECIPE, kind="Recipe")

    assert "bake for 50 minutes" in rendered, "the recipe steps did not reach the caller"
    assert "British" in rendered
    assert "Dessert" in rendered


def test_the_friendly_labels_survived_the_switch_to_default_keep() -> None:
    """Anti-vacuity: default-keep must not mean raw schema keys everywhere.

    The allowlist's one real contribution was readable labels. Keeping them as a
    LABEL table rather than a gate is the whole point — every other field still
    renders.
    """
    rendered = _single_entity_md(_RECIPE, kind="Recipe")
    assert "**Yield:**" in rendered
    assert "**Ingredients:**" in rendered
    assert "**Instructions:**" in rendered
    assert "**recipeYield:**" not in rendered


def test_an_over_cap_value_is_truncated_not_dropped() -> None:
    """The silent loss hiding inside the entity renderer itself.

    `if len(s) <= _ENTITY_VALUE_CAP` had no `else`, so a field OVER the cap
    vanished entirely rather than being cut. On a real recipe that is the whole
    ingredient list — thirty items joined comfortably exceed 500 characters — and
    the caller could not tell the field was absent from the PAGE versus dropped
    on the way out (ADR-0009).
    """
    entry = {"@type": "Product", "name": "X", "material": "y" * (_ENTITY_VALUE_CAP * 2)}
    rendered = _single_entity_md(entry, kind="Product")

    assert "material" in rendered, "an over-cap field vanished instead of being truncated"
    assert "…" in rendered, "truncation must be visible, not silent"
    assert "y" * (_ENTITY_VALUE_CAP + 1) not in rendered


def test_a_within_cap_value_is_untouched() -> None:
    """Anti-vacuity: the cap must bound, not rewrite."""
    entry = {"@type": "Product", "name": "X", "material": "brushed steel"}
    rendered = _single_entity_md(entry, kind="Product")
    assert "**material:** brushed steel" in rendered
    assert "…" not in rendered
