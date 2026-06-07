"""JSON-LD Recipe synthesis + default-keep entity rendering (ADR-0004 json half,
change `answer-bearing-json-rendering`).

The JSON-LD adapter must render the `Recipe` type — incl. its
`NutritionInformation` answer-bearing subobject — and must render single
entities by default-keep (every answer-bearing field minus known noise), NOT a
fixed `interesting_keys` allowlist. Backstops the captured regression
`regression/recipe-nutrition-volume-gate`, where the answer (`268 calories`)
lived in a `Recipe` payload the adapter previously dropped.
"""

from __future__ import annotations

from a2web.domain import json_to_markdown_rows
from a2web.packages.json_in_script import JsonPayload


def _ld(data: dict) -> JsonPayload:
    return JsonPayload(source="ld_json", data=data, script_id=None, byte_size=len(str(data)))


_RECIPE = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Brilliant banana loaf",
    "description": "A moist banana loaf.",
    "recipeYield": "8 slices",
    "totalTime": "PT1H10M",
    "recipeIngredient": ["3 ripe bananas", "140g butter"],
    "nutrition": {
        "@type": "NutritionInformation",
        "calories": "268 calories",
        "sugarContent": "24 grams sugar",
        "fatContent": "13 grams fat",
    },
}


def test_recipe_nutrition_is_rendered() -> None:
    out = json_to_markdown_rows(_ld(_RECIPE))
    assert out, "Recipe payload rendered nothing (previously dropped)"
    assert "268 calories" in out
    assert "24 grams sugar" in out
    assert "Brilliant banana loaf" in out


def test_recipe_without_nutrition_still_renders() -> None:
    payload = {k: v for k, v in _RECIPE.items() if k != "nutrition"}
    out = json_to_markdown_rows(_ld(payload))
    assert "Brilliant banana loaf" in out
    assert "calories" not in out  # omitted, not faked


def test_single_entity_render_is_default_keep() -> None:
    # `gtin13` is a real answer-bearing field outside the old `interesting_keys`
    # allowlist — default-keep must surface it.
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Widget",
        "gtin13": "4006381333931",
        "color": "blue",
        "image": "https://cdn.example/widget.jpg",
    }
    out = json_to_markdown_rows(_ld(product))
    assert "4006381333931" in out, "answer-bearing field outside the old allowlist was dropped"
    assert "blue" in out
    # Known noise dropped:
    assert "cdn.example" not in out
    assert "@type" not in out
