"""JSON-in-script extractor — package-level unit tests.

Covers spec scenarios from openspec/changes/harsh-test-session-fixes/specs/json-extract/spec.md.
"""

from __future__ import annotations

from a2web.packages.json_in_script import (
    JsonPayload,
    extract_json_payloads,
    rank_payloads,
)
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def test_next_data_detected_from_trendyol_fixture() -> None:
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    payloads = extract_json_payloads(html)
    next_data = [p for p in payloads if p.source == "next_data"]
    assert len(next_data) == 1
    p = next_data[0]
    assert p.script_id == "__NEXT_DATA__"
    assert isinstance(p.data, dict)
    assert "props" in p.data
    assert p.data["props"]["pageProps"]["products"][0]["brand"] == "adidas"
    assert p.byte_size > 0


def test_ld_json_product_detected() -> None:
    html = (_FIX / "ld_json_product.html").read_text()
    payloads = extract_json_payloads(html)
    ld = [p for p in payloads if p.source == "ld_json"]
    assert len(ld) == 1
    assert ld[0].data["@type"] == "Product"
    assert ld[0].data["aggregateRating"]["ratingValue"] == "4.8"


def test_generic_application_json_detected_yandex_shape() -> None:
    html = (_FIX / "yandex_market_generic.html").read_text()
    payloads = extract_json_payloads(html)
    generic = [p for p in payloads if p.source == "generic"]
    assert len(generic) == 1
    assert generic[0].data["products"][0]["name"] == "Mark Ryden MR9031Y_SJ"


def test_malformed_json_silently_skipped() -> None:
    html = (
        "<html><body>"
        '<script id="__NEXT_DATA__" type="application/json">{"valid":true}</script>'
        '<script type="application/ld+json">this is not json {{</script>'
        '<script type="application/ld+json">{"@type":"Article","headline":"ok"}</script>'
        "</body></html>"
    )
    payloads = extract_json_payloads(html)
    # Two valid: the __NEXT_DATA__ + the second ld+json. Malformed one is dropped.
    sources = [p.source for p in payloads]
    assert sources.count("next_data") == 1
    assert sources.count("ld_json") == 1


def test_empty_html_returns_empty_list() -> None:
    assert extract_json_payloads("") == []
    assert extract_json_payloads("<html><body><p>plain</p></body></html>") == []


def test_root_scalar_json_rejected() -> None:
    """JSON whose root is a bare number/string isn't useful — skipped."""
    html = '<script type="application/json">42</script>'
    assert extract_json_payloads(html) == []


def test_rank_payloads_prefers_strong_ld_json() -> None:
    """LD-JSON Product with ≥3 populated fields beats __NEXT_DATA__."""
    strong_ld = JsonPayload(
        source="ld_json",
        data={
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "X",
            "brand": "Y",
            "offers": {"price": 1},
            "aggregateRating": {"ratingValue": "4.5"},
        },
        script_id=None,
        byte_size=200,
    )
    next_data = JsonPayload(
        source="next_data",
        data={"props": {"pageProps": {"products": [1, 2, 3]}}},
        script_id="__NEXT_DATA__",
        byte_size=1000,
    )
    ranked = rank_payloads([next_data, strong_ld])
    assert ranked[0] is strong_ld
    assert ranked[1] is next_data


def test_rank_payloads_weak_ld_json_loses_to_next_data() -> None:
    """LD-JSON with only @type+@context loses to a populated next_data."""
    weak_ld = JsonPayload(
        source="ld_json",
        data={"@context": "https://schema.org", "@type": "WebSite", "name": "x"},
        script_id=None,
        byte_size=80,
    )
    next_data = JsonPayload(
        source="next_data",
        data={"props": {"pageProps": {"products": [1]}}},
        script_id="__NEXT_DATA__",
        byte_size=500,
    )
    ranked = rank_payloads([weak_ld, next_data])
    assert ranked[0] is next_data
    assert ranked[1] is weak_ld


def test_rank_handles_ld_json_graph_envelope() -> None:
    """Real-world LD-JSON nests inside @graph — recognizer walks one level down."""
    ld_graph = JsonPayload(
        source="ld_json",
        data={
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "x"},  # weak
                {
                    "@type": "Product",
                    "name": "P",
                    "brand": "B",
                    "offers": {"price": 1},
                    "aggregateRating": {"ratingValue": "5"},
                },
            ],
        },
        script_id=None,
        byte_size=400,
    )
    generic = JsonPayload(source="generic", data={"x": 1}, script_id=None, byte_size=20)
    ranked = rank_payloads([generic, ld_graph])
    assert ranked[0] is ld_graph


def test_rank_within_bucket_prefers_larger() -> None:
    a = JsonPayload(source="generic", data={"a": 1}, script_id=None, byte_size=100)
    b = JsonPayload(source="generic", data={"b": 1}, script_id=None, byte_size=5000)
    ranked = rank_payloads([a, b])
    assert ranked[0] is b
    assert ranked[1] is a


def test_window_var_state_assignment_detected() -> None:
    """`window.state = {...}` inside a text/javascript script is extracted."""
    html = (
        "<html><body>"
        '<script type="text/javascript">'
        'window.state = {"products":[{"name":"X","price":10}],"pageId":"search"};'
        "</script>"
        "</body></html>"
    )
    payloads = extract_json_payloads(html)
    wv = [p for p in payloads if p.source == "window_var"]
    assert len(wv) == 1
    assert wv[0].script_id == "state"
    assert wv[0].data["products"][0]["name"] == "X"


def test_window_var_initial_state_with_strings_containing_braces() -> None:
    """String-aware bracket counting handles braces inside string literals."""
    html = '<script type="text/javascript">window.__INITIAL_STATE__ = {"label":"a{b}c","items":[{"id":1}]};var other = 42;</script>'
    payloads = extract_json_payloads(html)
    wv = [p for p in payloads if p.source == "window_var"]
    assert len(wv) == 1
    assert wv[0].data["items"][0]["id"] == 1
    assert wv[0].data["label"] == "a{b}c"


def test_window_var_not_extracted_when_followed_by_code_not_object() -> None:
    """`window.state = computeState()` (function call) is silently skipped."""
    html = "<script>window.state = computeState();</script>"
    assert [p for p in extract_json_payloads(html) if p.source == "window_var"] == []


def test_window_var_unknown_name_not_scanned() -> None:
    """Random `window.foo = {...}` (not in seed list) is not picked up."""
    html = '<script>window.foo = {"a":1};</script>'
    assert [p for p in extract_json_payloads(html) if p.source == "window_var"] == []


def test_window_var_ranks_after_ld_json_and_next_data() -> None:
    """LD-JSON strong > next_data > weak LD > window_var > generic."""
    from a2web.packages.json_in_script import JsonPayload, rank_payloads

    wv = JsonPayload(source="window_var", data={"x": 1}, script_id="state", byte_size=100)
    nd = JsonPayload(source="next_data", data={"x": 1}, script_id="__NEXT_DATA__", byte_size=100)
    ranked = rank_payloads([wv, nd])
    assert ranked[0] is nd
    assert ranked[1] is wv
