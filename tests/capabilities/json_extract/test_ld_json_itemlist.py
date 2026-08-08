"""JSON-LD `ItemList` synthesis — `json_to_markdown_rows`.

`json_in_html` already detects `ld_json` payloads and `rank_payloads`
already prefers `ItemList`; this covers the synthesis adapter rendering an
`ItemList` into record rows, including the commerce offer-lift (price,
currency, url) and linked-record rendering.
"""

from __future__ import annotations

import json
import re

from json_in_html import JsonPayload

from a2web.packages.structured_render import json_to_markdown_rows, listing_rows
from tests.fixtures import FIXTURES_DIR


def _ld_payload(data: dict) -> JsonPayload:
    return JsonPayload(source="ld_json", data=data, script_id=None, byte_size=len(str(data)))


def _hepsiburada_itemlist() -> dict:
    """Parse the real JSON-LD `ItemList` out of the trimmed fixture."""
    html = (FIXTURES_DIR / "hepsiburada_listing.html").read_text()
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert block is not None
    return json.loads(block.group(1))


def test_itemlist_renders_record_rows() -> None:
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {"name": "First item", "url": "https://example.com/1"}},
            {"@type": "ListItem", "position": 2, "item": {"name": "Second item", "url": "https://example.com/2"}},
            {"@type": "ListItem", "position": 3, "item": {"name": "Third item", "url": "https://example.com/3"}},
        ],
    }
    md = json_to_markdown_rows(_ld_payload(data))
    assert "First item" in md
    assert "Third item" in md
    assert "https://example.com/1" in md


def test_product_itemlist_lifts_price_and_url() -> None:
    """Real Hepsiburada ItemList: each Product carries name + offers.{price,
    priceCurrency, url}. The synth must surface a linked record with the
    combined price token and the product url, and must drop the image."""
    md = json_to_markdown_rows(_ld_payload(_hepsiburada_itemlist()))
    # combined price token (price + currency)
    assert "3690 TRY" in md
    # product url present as a markdown link target
    assert "-pm-HBC" in md
    assert re.search(r"\[[^\]]+\]\(https://www\.hepsiburada\.com/[^\s)]+-pm-HBC[^\s)]*\)", md)
    # image CDN urls are token noise — never emitted
    assert "productimages.hepsiburada.net" not in md


def test_long_product_url_not_truncated() -> None:
    """A product url longer than the table's 80-char cell cap must survive
    verbatim in the linked-record form, else try_url re-breaks."""
    item = _hepsiburada_itemlist()
    urls = [e["item"]["offers"]["url"] for e in item["itemListElement"]]
    longest = max(urls, key=len)
    assert len(longest) > 80  # fixture guarantees this
    md = json_to_markdown_rows(_ld_payload(item))
    assert longest in md


def test_aggregate_rating_lifted_when_present() -> None:
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "item": {
                    "name": "Rated Mic",
                    "offers": {"price": 100, "priceCurrency": "TRY", "url": "https://x.test/p-pm-AAA"},
                    "aggregateRating": {"ratingValue": "4.7", "reviewCount": 12},
                },
            },
            {
                "@type": "ListItem",
                "item": {
                    "name": "Unrated Mic",
                    "offers": {"price": 50, "priceCurrency": "TRY", "url": "https://x.test/q-pm-BBB"},
                },
            },
        ],
    }
    md = json_to_markdown_rows(_ld_payload(data))
    assert "4.7" in md
    # the unrated row still renders cleanly (no stray rating glyph dangling)
    assert "Unrated Mic" in md


def test_non_commerce_itemlist_keeps_table() -> None:
    """Rows with neither a lifted price nor url stay in the fixed-width
    markdown table rendering — no regression for generic index lists."""
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "item": {"name": "Chapter One", "position": 1}},
            {"@type": "ListItem", "item": {"name": "Chapter Two", "position": 2}},
        ],
    }
    md = json_to_markdown_rows(_ld_payload(data))
    assert "| name" in md  # table header, not a linked record
    assert "- [Chapter One]" not in md


def test_link_text_sanitized() -> None:
    """A name with ] / ) / newline must not break the markdown link."""
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "item": {
                    "name": "Weird ] name ) with\nnewline",
                    "offers": {"price": 9, "priceCurrency": "TRY", "url": "https://x.test/z-pm-CCC"},
                },
            },
        ],
    }
    md = json_to_markdown_rows(_ld_payload(data))
    # the url survives intact and the link parses (closing ) of the link is the url's)
    assert "https://x.test/z-pm-CCC" in md
    assert re.search(r"\[[^\]\n]+\]\(https://x\.test/z-pm-CCC\)", md)


def test_normalized_rows_carry_price_and_currency_as_separate_fields() -> None:
    """`type-listing-commerce-fields`: the wire's `ListingOption` wants price
    and currency apart, even though the synthetic markdown still joins them
    (the combined-token behavior is covered by `test_product_itemlist_lifts_price_and_url`)."""
    rows = listing_rows(_ld_payload(_hepsiburada_itemlist()))
    assert rows, "fixture must yield rows"
    lifted = [r for r in rows if r.get("price") is not None]
    assert lifted
    for row in lifted:
        assert row["price"] == "3690" or row["price"].isdigit() or row["price"].replace(".", "", 1).isdigit()
        assert " " not in row["price"], "price must not carry the currency inline"
    assert any(row.get("currency") == "TRY" for row in lifted)


def test_availability_and_seller_lifted_when_present() -> None:
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "item": {
                    "name": "In-stock item",
                    "offers": {
                        "price": 100,
                        "priceCurrency": "TRY",
                        "url": "https://x.test/p-pm-AAA",
                        "availability": "https://schema.org/InStock",
                        "seller": {"@type": "Organization", "name": "Acme Store"},
                    },
                },
            },
            {
                "@type": "ListItem",
                "item": {
                    "name": "No stock info",
                    "offers": {"price": 50, "priceCurrency": "TRY", "url": "https://x.test/q-pm-BBB"},
                },
            },
        ],
    }
    rows = listing_rows(_ld_payload(data))
    assert len(rows) == 2
    stocked, bare = rows
    assert stocked["stock"] == "InStock"
    assert stocked["seller"] == "Acme Store"
    # honest gap: no availability/seller declared at this level -> absent, not fabricated
    assert "stock" not in bare
    assert "seller" not in bare


def test_bare_string_seller_lifted() -> None:
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "item": {
                    "name": "Plain seller item",
                    "offers": {"price": 20, "priceCurrency": "TRY", "url": "https://x.test/r-pm-CCC", "seller": "Some Seller"},
                },
            },
        ],
    }
    rows = listing_rows(_ld_payload(data))
    assert rows[0]["seller"] == "Some Seller"


def test_empty_itemlist_yields_no_rows() -> None:
    md = json_to_markdown_rows(_ld_payload({"@type": "ItemList", "itemListElement": []}))
    assert md == ""


def test_malformed_itemlist_yields_no_rows() -> None:
    md = json_to_markdown_rows(_ld_payload({"@type": "ItemList", "itemListElement": "not-a-list"}))
    assert md == ""
