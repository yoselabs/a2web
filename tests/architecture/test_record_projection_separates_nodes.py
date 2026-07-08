"""Architectural invariant: the record-text projection separates DOM nodes.

Backstops the `typed-extraction-boundary` change (ADR-0003 / ADR-0004). The
class-C regression `regression/hepsiburada-listing-price` was caused by
`detector._own_text` flattening a record's descendant text with no separator,
fusing adjacent inline values (`890 TL` + `%21` + `700 TL` → `890 TL%21700 TL`)
so the extractor could not recover list-vs-sale.

This is a *behavioral* fitness function (implementation-agnostic): adjacent
inline element values MUST stay distinguishable through the public
`extract_records` projection, and strikethrough markup MUST be preserved. If a
refactor re-introduces a value-blind flatten, these fail — regardless of how
the projection is coded.

Acceptance check (re-run after any refactor):

    1. In `detector._own_text`, drop the element-boundary separator (revert to
       a no-separator flatten).
    2. Run `make arch`.
    3. Confirm this test fails.
    4. Revert.
"""

from __future__ import annotations

from record_mine import extract_records


def _listing(price_html: str) -> str:
    cards = "".join(
        f'<article class="prd"><h2><a href="/p{i}">Item {i}</a></h2><div class="price">{price_html}</div></article>' for i in range(6)
    )
    return f"<html><body><div class='grid'>{cards}</div></body></html>"


def test_adjacent_inline_values_do_not_fuse() -> None:
    rs = extract_records(_listing("<span>890 TL</span><span>%21</span><span>700 TL</span>"))
    assert rs is not None
    md = rs.to_markdown()
    assert "890 TL%21700" not in md, f"adjacent inline values fused:\n{md[:300]}"
    assert "%21" in md and "700 TL" in md


def test_strikethrough_markup_is_preserved() -> None:
    rs = extract_records(_listing("<del>890 TL</del><span>%21</span><span>700 TL</span>"))
    assert rs is not None
    assert "~~890 TL" in rs.to_markdown(), "strikethrough list price not marked"
