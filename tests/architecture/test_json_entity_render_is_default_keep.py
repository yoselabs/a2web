"""Architectural invariant: JSON-LD entity rendering is default-keep.

Backstops the `answer-bearing-json-rendering` change (ADR-0004 json half). The
class is the *value-blind structural-filter projection*: `_single_entity_md`
once rendered entities through a hardcoded `interesting_keys` allowlist, so any
answer-bearing field outside that fixed list (a `Recipe.nutrition`, a
`Product.gtin`) was silently dropped.

This is a *behavioral* fitness function (implementation-agnostic): an entity
field the renderer's author did not anticipate MUST still surface through the
public `json_to_markdown_rows`. If a fixed allowlist is re-introduced, the
randomized novel key vanishes and this fails — regardless of how the filter is
coded.

Acceptance check (re-run after any refactor):

    1. In `_single_entity_md`, re-add an `if key not in ALLOWLIST: continue`
       gate.
    2. Run `make arch`.
    3. Confirm `test_unanticipated_field_is_surfaced` fails.
    4. Revert.
"""

from __future__ import annotations

from json_in_html import JsonPayload

from a2web.domain import json_to_markdown_rows

# A scalar key chosen to NOT be in any plausible "interesting keys" allowlist —
# stable (not random, per the no-Math.random rule) but clearly unanticipated.
_NOVEL_KEY = "madeUpAnswerBearingField"
_NOVEL_VALUE = "load-bearing-value-42"


def test_unanticipated_field_is_surfaced() -> None:
    payload = JsonPayload(
        source="ld_json",
        data={
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Thing",
            _NOVEL_KEY: _NOVEL_VALUE,
        },
        script_id=None,
        byte_size=64,
    )
    out = json_to_markdown_rows(payload)
    assert _NOVEL_VALUE in out, "an unanticipated answer-bearing field was dropped — allowlist re-introduced?"
