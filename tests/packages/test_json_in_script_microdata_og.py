"""Microdata + OpenGraph extraction — selectolax-native, no extruct.

Covers the attribute-based structured-data sources that complement the
script-tag detectors. RDFa is intentionally out of scope (low real-world
hit rate; see openspec/changes/archive/2026-05-23-add-microdata-rdfa-extraction
design.md D1 for the inversion).
"""

from __future__ import annotations

from a2web.packages.json_in_script import (
    JsonPayload,
    extract_json_payloads,
    rank_payloads,
)

# --------------------------------------------------------------------- #
# Microdata
# --------------------------------------------------------------------- #


_MICRODATA_PRODUCT_HTML = """
<html><body>
  <div itemscope itemtype="https://schema.org/Product">
    <h1 itemprop="name">Stratos Hiking Boot</h1>
    <meta itemprop="sku" content="SK-2117">
    <img itemprop="image" src="https://example.com/boot.jpg">
    <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
      <meta itemprop="priceCurrency" content="USD">
      <span itemprop="price">189.00</span>
      <link itemprop="availability" href="https://schema.org/InStock">
    </div>
    <div itemprop="aggregateRating" itemscope itemtype="https://schema.org/AggregateRating">
      <meta itemprop="ratingValue" content="4.7">
      <meta itemprop="reviewCount" content="312">
    </div>
  </div>
</body></html>
"""


def test_microdata_product_is_extracted() -> None:
    payloads = extract_json_payloads(_MICRODATA_PRODUCT_HTML)
    micro = [p for p in payloads if p.source == "microdata"]
    assert len(micro) == 1
    items = micro[0].data
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["type"] == ["https://schema.org/Product"]
    props = item["properties"]
    assert props["name"] == "Stratos Hiking Boot"
    assert props["sku"] == "SK-2117"
    assert props["image"] == "https://example.com/boot.jpg"
    # nested itemscope → nested dict
    assert isinstance(props["offers"], dict)
    assert props["offers"]["properties"]["price"] == "189.00"
    assert props["offers"]["properties"]["priceCurrency"] == "USD"
    assert props["aggregateRating"]["properties"]["ratingValue"] == "4.7"


def test_microdata_strong_outranks_next_data() -> None:
    """A strong microdata Product (bucket 1) wins over next_data (bucket 2)."""
    html = _MICRODATA_PRODUCT_HTML + '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}}}</script>'
    ranked = rank_payloads(extract_json_payloads(html))
    assert ranked[0].source == "microdata"


def test_microdata_weak_loses_to_next_data() -> None:
    """Microdata Product with <3 fields drops to bucket 4; next_data (bucket 2) wins."""
    html = """
    <html><body>
      <div itemscope itemtype="https://schema.org/Product">
        <span itemprop="name">Bare item</span>
      </div>
      <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"x":1}}}</script>
    </body></html>
    """
    ranked = rank_payloads(extract_json_payloads(html))
    assert ranked[0].source == "next_data"


def test_microdata_unknown_type_falls_to_weak_bucket() -> None:
    html = """
    <html><body>
      <div itemscope itemtype="https://schema.org/LocalBusiness">
        <span itemprop="name">Some place</span>
        <span itemprop="address">123 Main St</span>
        <span itemprop="telephone">555-0100</span>
      </div>
    </body></html>
    """
    payloads = extract_json_payloads(html)
    micro = [p for p in payloads if p.source == "microdata"]
    assert len(micro) == 1
    # LocalBusiness is not in the preferred set → weak bucket
    ranked = rank_payloads(payloads)
    assert ranked[0].source == "microdata"  # only payload, but in bucket 4


def test_microdata_nested_scope_not_emitted_as_top_level() -> None:
    """The nested Offer inside Product is NOT a separate top-level item."""
    payloads = extract_json_payloads(_MICRODATA_PRODUCT_HTML)
    micro = [p for p in payloads if p.source == "microdata"]
    items = micro[0].data
    assert len(items) == 1  # only the outer Product, not Offer/AggregateRating


# --------------------------------------------------------------------- #
# OpenGraph
# --------------------------------------------------------------------- #


def test_opengraph_meta_tags_are_collected() -> None:
    html = """
    <html><head>
      <meta property="og:title" content="The Boots Article">
      <meta property="og:type" content="product">
      <meta property="og:url" content="https://example.com/p/123">
      <meta property="product:price:amount" content="189.00">
      <meta property="article:tag" content="hiking">
    </head><body></body></html>
    """
    payloads = extract_json_payloads(html)
    og = [p for p in payloads if p.source == "opengraph"]
    assert len(og) == 1
    data = og[0].data
    assert isinstance(data, dict)
    assert data["og:title"] == "The Boots Article"
    assert data["og:type"] == "product"
    assert data["product:price:amount"] == "189.00"
    assert data["article:tag"] == "hiking"


def test_opengraph_ranks_after_framework_state() -> None:
    """OG (bucket 3) sits behind next_data (bucket 2)."""
    html = """
    <html><head>
      <meta property="og:title" content="hi">
      <meta property="og:type" content="article">
    </head><body>
      <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}}}</script>
    </body></html>
    """
    ranked = rank_payloads(extract_json_payloads(html))
    sources = [p.source for p in ranked]
    assert sources.index("next_data") < sources.index("opengraph")


def test_opengraph_irrelevant_meta_tags_skipped() -> None:
    """Non-OG meta tags (e.g. viewport, description) must NOT be emitted."""
    html = """
    <html><head>
      <meta name="description" content="something">
      <meta name="viewport" content="width=device-width">
      <meta property="twitter:card" content="summary">
    </head></html>
    """
    payloads = extract_json_payloads(html)
    og = [p for p in payloads if p.source == "opengraph"]
    assert og == []


# --------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------- #


def test_page_with_no_structured_data_returns_empty() -> None:
    html = "<html><body><p>Just text.</p></body></html>"
    assert extract_json_payloads(html) == []


def test_empty_html_returns_empty() -> None:
    assert extract_json_payloads("") == []


def test_microdata_strong_with_three_populated_fields_passes_gate() -> None:
    """Sanity check on the _microdata_strong threshold."""
    payloads = extract_json_payloads(_MICRODATA_PRODUCT_HTML)
    micro = [p for p in payloads if p.source == "microdata"]
    ranked = rank_payloads([JsonPayload(source="next_data", data={"x": 1}, script_id=None, byte_size=10), *micro])
    assert ranked[0].source == "microdata"  # bucket 1 beats bucket 2
