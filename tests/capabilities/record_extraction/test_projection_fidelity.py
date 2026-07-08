"""Projection fidelity — the record text projection must not fuse distinct DOM
text nodes and must preserve strikethrough markup.

Born from the `regression/hepsiburada-listing-price` class-C bug: a discounted
product card renders `<del>890 TL</del><span>%21</span><span>700 TL</span>` with
no whitespace between the inline elements, and the value-blind `"".join`
projection fused them into `890 TL%21700 TL` — destroying both the node
boundary and the list-vs-sale (strikethrough) distinction before the extractor
ever saw the content. See ADR-0003 / ADR-0004.
"""

from __future__ import annotations

from record_mine import extract_records


def _discount_card(i: int) -> str:
    # Inline price elements with NO whitespace text node between them — the
    # exact shape that fuses under a no-separator projection.
    return (
        '<article class="prd">'
        f'<h2 class="title"><a href="/p{i}">Wireless Earbuds Model {i}</a></h2>'
        '<div class="price"><del>890 TL</del><span class="badge">%21</span>'
        '<span class="sale">700 TL</span></div>'
        "</article>"
    )


_LISTING = "<html><body><div class='grid'>" + "".join(_discount_card(i) for i in range(6)) + "</div></body></html>"


def test_adjacent_inline_values_do_not_fuse() -> None:
    rs = extract_records(_LISTING)
    assert rs is not None
    md = rs.to_markdown()
    # The discount badge must not merge into the sale price.
    assert "890 TL%21700" not in md, f"prices fused in projection:\n{md[:400]}"
    # Each distinct value survives as a recoverable token.
    assert "%21" in md
    assert "700 TL" in md


def test_strikethrough_list_price_is_marked() -> None:
    rs = extract_records(_LISTING)
    assert rs is not None
    md = rs.to_markdown()
    # The struck-through original price is marked so list != sale is recoverable.
    assert "~~890 TL" in md, f"strikethrough not preserved:\n{md[:400]}"
