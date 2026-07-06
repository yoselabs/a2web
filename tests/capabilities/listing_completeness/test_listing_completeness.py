"""listing-completeness: honest partial-listing signal (Slice 1).

The sufficiency axis — a listing can render cleanly, pass every gate, carry
real records, and still be PARTIAL because infinite-scroll / lazy-load only
materialised the first batch. These tests pin the regression that motivated
the change: a Hepsiburada search returned "31 listings" with `confidence:
high` while the live page held 40 — and nothing signalled the shortfall.

`listing_oracle` is unit-tested pure; the fetch/ask paths are driven through
the in-process MCP transport (the exact wire an agent receives).
"""

from __future__ import annotations

import pytest

from a2web.listing_oracle import listing_oracle
from tests.capabilities.ask_response.test_ask_response import _MINIMAL_HTML, _ask_wire
from tests.capabilities.fetch_response.test_fetch_response import _fetch_raw_wire


def _listing_html(n_records: int, *, oracle_jsonld: int | None = None, oracle_visible: str | None = None) -> bytes:
    """A listing page with `n_records` detectable records and an optional oracle.

    Each row carries a heading link plus >20 chars of own text so the record
    detector fires (`_MIN_RECORDS=5`, `_MIN_RECORD_TEXT=20`, own-link required).
    """
    rows = "".join(
        f'<li class="product-card"><h3><a href="/product/{i}">Aerator {i}</a></h3>'
        f"<p>Water saving faucet aerator, ic disli, model number {i}</p></li>"
        for i in range(n_records)
    )
    head = ""
    if oracle_jsonld is not None:
        head += f'<script type="application/ld+json">{{"@type":"ItemList","numberOfItems":{oracle_jsonld}}}</script>'
    if oracle_visible is not None:
        head += f'<div class="result-count">{oracle_visible}</div>'
    return (f"<html><body><main>{head}<ul>{rows}</ul></main></body></html>").encode()


# --------------------------------------------------------------------- #
# listing_oracle — pure item-count extraction
# --------------------------------------------------------------------- #


def test_oracle_reads_jsonld_number_of_items() -> None:
    html = '<script type="application/ld+json">{"@type":"ItemList","numberOfItems":40}</script>'
    assert listing_oracle(html) == 40


def test_oracle_reads_visible_turkish_count() -> None:
    assert listing_oracle("<div>40 sonuç bulundu</div>") == 40


def test_oracle_reads_visible_english_count_with_separator() -> None:
    assert listing_oracle("<div>1,234 results</div>") == 1234


def test_oracle_reads_showing_of_total() -> None:
    assert listing_oracle("<div>Showing 1-24 of 40 products</div>") == 40


def test_oracle_ignores_review_and_rating_numbers() -> None:
    # "reviews" / "rating" are not item nouns — a bare popularity number must
    # NOT be misread as an item oracle.
    assert listing_oracle("<div>1000 reviews, 4.7 rating</div>") is None


def test_oracle_none_on_article() -> None:
    assert listing_oracle("<p>Just an article with no counts at all.</p>") is None


def test_oracle_structured_wins_over_visible() -> None:
    html = '<script type="application/ld+json">{"@type":"ItemList","numberOfItems":40}</script><div>about 12 results</div>'
    assert listing_oracle(html) == 40


# --------------------------------------------------------------------- #
# fetch_raw path — the regression: partial listing is NEVER silent
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_partial_listing_surfaces_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # 31 records parsed, page advertises 40 (31/40 = 0.775 < 0.9 tolerance).
    body = _listing_html(31, oracle_jsonld=40, oracle_visible="40 sonuç")
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://shop.example/search?q=aerator")

    assert data["items_loaded"] == 31
    assert data["items_total"] == 40
    codes = [h["code"] for h in data["operator_hints"]]
    assert "listing_partial" in codes
    # A partial listing returned real records — it is an info signal, NOT a wall.
    assert "retrieval_incomplete" not in data
    assert data.get("status") != "failed"


@pytest.mark.asyncio
async def test_fetch_raw_partial_via_visible_count_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # No structured count — the visible "40 sonuç" is the oracle.
    body = _listing_html(31, oracle_visible="40 sonuç")
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://shop.example/ara?q=aerator")
    assert data["items_loaded"] == 31
    assert data["items_total"] == 40
    assert "listing_partial" in [h["code"] for h in data["operator_hints"]]


@pytest.mark.asyncio
async def test_fetch_raw_complete_listing_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 40 of 40 → complete → no item fields, no partial hint.
    body = _listing_html(40, oracle_jsonld=40)
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://shop.example/search?q=aerator")
    assert "items_loaded" not in data
    assert "items_total" not in data
    assert "listing_partial" not in [h["code"] for h in data.get("operator_hints", [])]


@pytest.mark.asyncio
async def test_fetch_raw_non_listing_has_no_item_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    # An article produces no RecordSet — the item fields must be absent even if
    # a stray number appears on the page.
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://blog.example/post")
    assert "items_loaded" not in data
    assert "items_total" not in data


# --------------------------------------------------------------------- #
# ask path — the signal rides the lean envelope too
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_partial_listing_surfaces_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _listing_html(31, oracle_jsonld=40)
    data = await _ask_wire(
        monkeypatch,
        body=body,
        url="https://shop.example/search?q=aerator",
        question="List the water-saving aerators.",
    )
    assert data["items_loaded"] == 31
    assert data["items_total"] == 40
    assert "listing_partial" in [h["code"] for h in data["operator_hints"]]
    # Sufficiency signal is info — it must not flip the ask into an incomplete wall.
    assert "retrieval_incomplete" not in data
