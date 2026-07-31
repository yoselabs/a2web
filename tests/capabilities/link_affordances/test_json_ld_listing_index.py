"""A JSON-LD listing must leave an index, exactly as a DOM-mined one does (ADR-0015).

`json_to_markdown_rows` renders an embedded `ItemList` into rich markdown — name,
url, price, rating per item — and then returns a STRING, throwing the structure
away. The DOM record-miner keeps its `RecordSet`, so it feeds `other_pages` and
the `options` shelf. The JSON-LD path fed neither.

The consequence is ADR-0015's harm precisely: `query` withholds the page body by
default, so the caller — itself an agent that never sees the body — is blind to
everything the answer did not surface. On a commerce or SSR'd catalog page (the
shape where `ItemList` is the norm) every product URL sat in the rendered
markdown and reached the caller nowhere. The answer looked complete and the
index was silently empty.

The fix converges both paths on `RecordSet` rather than deriving the index twice,
so `_records_to_next_links` and `_records_to_options` apply unchanged — which is
what `test_both_paths_yield_the_same_index` pins.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from record_mine import RecordSet

from a2web.fetcher import ContentCandidate, _escalate_via_json, _rows_to_record_set, _run_extraction_escalation
from a2web.fetcher_response import _records_to_options
from a2web.models import NextLink

_BASE = "https://shop.example.com/catalog"

# Five items, not three: the DOM record-miner needs a record region of at least
# five siblings before it will call one dominant, so a shorter fixture would
# leave the DOM half of the equivalence witness silently unmined — the witness
# would pass while comparing against nothing.
_ITEMS = (
    ("Alpha Widget", "https://shop.example.com/p/alpha", "1990", "4.6"),
    ("Beta Widget", "https://shop.example.com/p/beta", "2490", "4.2"),
    ("Gamma Widget", "https://shop.example.com/p/gamma", "3190", None),
    ("Delta Widget", "https://shop.example.com/p/delta", "4290", "4.8"),
    ("Epsilon Widget", "https://shop.example.com/p/epsilon", "5490", "3.9"),
)


def _ld_json_page() -> str:
    """A catalog whose items live ONLY in JSON-LD — no mineable DOM records."""
    elements = ",".join(
        f'{{"@type":"ListItem","position":{i + 1},"item":{{"@type":"Product","name":"{name}","url":"{url}",'
        f'"offers":{{"@type":"Offer","price":"{price}","priceCurrency":"TRY"}}'
        + (f',"aggregateRating":{{"ratingValue":"{rating}"}}' if rating else "")
        + "}}"
        for i, (name, url, price, rating) in enumerate(_ITEMS)
    )
    return (
        "<html><body><h1>Catalog</h1>"
        '<script type="application/ld+json">'
        f'{{"@context":"https://schema.org","@type":"ItemList","itemListElement":[{elements}]}}'
        "</script></body></html>"
    )


def _dom_page() -> str:
    """The SAME items as mineable DOM records — the path that already worked."""
    rows = "".join(
        f"<article class='row'><h3><a href='{url}'>{name}</a></h3>"
        f"<p>{price} TRY{f' rating {rating}' if rating else ''}</p></article>"
        for name, url, price, rating in _ITEMS
    )
    return f"<html><body><h1>Catalog</h1><div class='listing'>{rows}</div></body></html>"


@dataclass
class _FakeFc:
    """The subset of `FetchContext` the escalation touches."""

    content_md: str = ""
    final_url: str = _BASE
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)
    content_candidates: list[ContentCandidate] = field(default_factory=list)
    record_set: RecordSet | None = None
    record_count: int | None = None


async def test_json_ld_listing_populates_other_pages() -> None:
    """THE regression: before the fix this list was empty on a JSON-LD catalog."""
    fc = _FakeFc()
    await _run_extraction_escalation(fc, raw_html=_ld_json_page())  # type: ignore[arg-type]

    urls = [link.url for link in fc.next_links_handler]
    assert urls == [url for _, url, _, _ in _ITEMS], f"every item URL must reach the caller, got {urls}"


async def test_json_ld_listing_populates_the_option_shelf() -> None:
    """`options` is the same-page half of the index — also empty before the fix."""
    fc = _FakeFc()
    await _run_extraction_escalation(fc, raw_html=_ld_json_page())  # type: ignore[arg-type]

    assert fc.record_set is not None, "the structure behind the render must survive"
    options = _records_to_options(fc.record_set)
    assert [o.title for o in options] == [name for name, _, _, _ in _ITEMS]
    # Page order preserved — a2web presents, it does not rank (ADR-0012).
    assert options[0].url == _ITEMS[0][1]
    # The price/rating signal the markdown shows must also reach the shelf,
    # or the caller sees titles with nothing to distinguish them by.
    assert "1990" in options[0].detail


async def test_both_paths_yield_the_same_index() -> None:
    """Task 1.4's witness, written BEFORE the lift that will move this code.

    The same catalog reachable two ways must produce the same index. This is
    what makes converging on `RecordSet` worth it rather than deriving
    `other_pages` and `options` separately per path — two derivations drift,
    and the drift would be invisible on any page that only has one path.
    """
    ld_fc, dom_fc = _FakeFc(), _FakeFc()
    await _run_extraction_escalation(ld_fc, raw_html=_ld_json_page())  # type: ignore[arg-type]
    await _run_extraction_escalation(dom_fc, raw_html=_dom_page())  # type: ignore[arg-type]

    assert dom_fc.record_set is not None, "non-vacuous: the DOM path must actually mine this page"
    assert [link.url for link in ld_fc.next_links_handler] == [link.url for link in dom_fc.next_links_handler]
    assert [o.title for o in _records_to_options(ld_fc.record_set)] == [o.title for o in _records_to_options(dom_fc.record_set)]


async def test_dom_records_keep_precedence_when_both_exist() -> None:
    """The fix is strictly ADDITIVE — it may never replace an index that shipped.

    A page carrying both a JSON-LD `ItemList` and mineable DOM records must
    still use the DOM set, so no page that already had an index sees it change.
    """
    ld_only = _ld_json_page().replace("</body></html>", "")
    combined = ld_only + _dom_page().split("<h1>Catalog</h1>", 1)[1]

    probe = _FakeFc()
    _, json_set = await _escalate_via_json(probe, raw_html=combined)  # type: ignore[arg-type]
    assert json_set is not None, "non-vacuous: the JSON-LD half must have parsed"

    fc = _FakeFc()
    await _run_extraction_escalation(fc, raw_html=combined)  # type: ignore[arg-type]

    assert fc.record_set is not None
    assert fc.record_set.container != "json-ld", "the DOM record set must win"


def test_a_single_product_is_not_a_listing() -> None:
    """An entity is not an index — a detail page must not fabricate one.

    Guards the other direction: `listing_rows` returning rows for every JSON-LD
    entity would put a single `Product` on the option shelf as if the page were
    a catalog of one.
    """
    from json_in_html import extract_json_payloads

    from a2web.domain import listing_rows

    html = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Solo Widget",'
        '"url":"https://shop.example.com/p/solo","offers":{"price":"999"}}'
        "</script></body></html>"
    )
    payloads = extract_json_payloads(html)
    assert payloads, "non-vacuous: the payload must parse"
    assert all(listing_rows(p) == [] for p in payloads)
    assert _rows_to_record_set([], base_url=_BASE) is None
