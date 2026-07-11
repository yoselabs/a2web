"""ask-retains-listing-options: rank-don't-skip.

`ask` keeps a ranked verdict in `answer` but stops deleting the field it ranked
over — a neutral, page-order `options` shelf rides the wire on a listing, absent
on non-listings, and never on the `fetch_raw` wire.
"""

from __future__ import annotations

import json

import pytest
from a2kit.testing import client as make_client
from a2kit.testing import lazy
from record_mine import Record, RecordSet

from a2web.fetcher_response import _records_to_options
from a2web.llm_resource import LlmExtractorResource
from a2web.server import build_app
from a2web.state import AppState
from a2web.tiers import REGISTRY
from tests.capabilities.ask_response.test_router_wire import _JsonEnvelopeProvider, _RawStub
from tests.capabilities.fetch_response.test_fetch_response import _fetch_raw_wire
from tests.capabilities.listing_completeness.test_listing_completeness import _listing_html


def _record(*, text: str, heading: str | None, url: str | None) -> Record:
    return Record(
        text=text,
        links=(),
        heading_text=heading,
        heading_link=(heading or "", url) if url else None,
        depth=0,
        markdown=f"- {heading or text}",
    )


def _rs(records: tuple[Record, ...]) -> RecordSet:
    return RecordSet(records=records, container="ul", child_signature="li", max_depth=0)


# --------------------------------------------------------------------- #
# _records_to_options — projection
# --------------------------------------------------------------------- #


def test_projection_preserves_page_order_and_fields() -> None:
    rs = _rs(
        (
            _record(text="4.6 (77) 329 TL", heading="Cortex RJ45", url="https://x/cortex"),
            _record(text="4.4 (259) 428 TL", heading="Wozlo RJ45", url="https://x/wozlo"),
        )
    )
    opts = _records_to_options(rs)
    assert [o.title for o in opts] == ["Cortex RJ45", "Wozlo RJ45"]  # page order, not re-ranked
    assert opts[0].url == "https://x/cortex"
    assert opts[0].detail == "4.6 (77) 329 TL"


def test_projection_none_and_empty() -> None:
    assert _records_to_options(None) == []
    assert _records_to_options(_rs(())) == []


def test_projection_text_lead_when_no_heading() -> None:
    opts = _records_to_options(_rs((_record(text="A premium crimper with no heading link", heading=None, url=None),)))
    assert opts[0].title  # falls back to a text lead
    assert opts[0].url is None


def test_projection_caps_the_set() -> None:
    many = tuple(_record(text=f"row {i}", heading=f"Item {i}", url=f"https://x/{i}") for i in range(80))
    opts = _records_to_options(_rs(many))
    assert len(opts) == 50  # _OPTIONS_CAP


def test_projection_strips_duplicated_title_from_detail() -> None:
    # record.text leads with the title; detail should carry only the signal after it.
    rs = _rs((_record(text="Cortex RJ45 Pense 4.6 (77) 329 TL", heading="Cortex RJ45 Pense", url="https://x/c"),))
    opts = _records_to_options(rs)
    assert opts[0].title == "Cortex RJ45 Pense"
    assert opts[0].detail == "4.6 (77) 329 TL"


def test_projection_normalizes_detail_whitespace() -> None:
    opts = _records_to_options(_rs((_record(text="  4.6   (77)\n\n 329 TL ", heading="X", url="https://x/1"),)))
    assert opts[0].detail == "4.6 (77) 329 TL"


# --------------------------------------------------------------------- #
# Wire — through the MCP transport
# --------------------------------------------------------------------- #

# `options` is gated on the LLM's page classification, so the wire tests drive a
# real router envelope (structural_form) — the plain-text `_StubProvider` leaves
# routing None, which now (correctly) suppresses the DOM-mined shelf.
_LISTING_ENVELOPE = {"answer": "Cortex leads by rating.", "structural_form": "listing", "shape": "records"}
_PRODUCT_ENVELOPE = {"answer": "Price: 42.00 TRY. In stock.", "structural_form": "product", "shape": "key-value"}


async def _ask_wire_classified(monkeypatch: pytest.MonkeyPatch, *, body: bytes, envelope: dict, **ask_kwargs: object) -> dict:
    """Drive `query` with a chosen body AND a chosen router classification."""
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body))
    app = build_app()
    state = await app.container().get(AppState)
    fake = LlmExtractorResource(state.settings, state.sqlite, lazy(_JsonEnvelopeProvider(envelope)))
    app.provide(LlmExtractorResource, lambda: fake)
    async with make_client(app) as client:
        wire = await client.call_wire("query", **ask_kwargs)
    return json.loads(wire)


@pytest.mark.asyncio
async def test_listing_ask_carries_options(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire_classified(
        monkeypatch,
        body=_listing_html(6),
        envelope=_LISTING_ENVELOPE,
        url="https://shop.example/ara?q=crimp&siralama=artanFiyat",
        query="which crimping tool is best?",
    )
    assert isinstance(data["options"], list)
    assert len(data["options"]) == 6  # every parsed record retained, none skipped
    for opt in data["options"]:
        assert "title" in opt


@pytest.mark.asyncio
async def test_product_page_footer_records_do_not_leak_as_options(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression (hepsiburada/koçtaş): the DOM record-miner fires on ANY repeated
    # DOM — a product page's site-wide footer megamenu parses into a full
    # record_set — but the LLM classifies the page as `product`. IDENTICAL body to
    # the listing case above (record_set populated), yet `options` MUST NOT ride
    # the wire, because the option shelf is trusted only when the model agrees the
    # page is a listing. Without the gate this leaked 10 null-url footer entries.
    data = await _ask_wire_classified(
        monkeypatch,
        body=_listing_html(6),  # same body → _options IS populated internally
        envelope=_PRODUCT_ENVELOPE,  # …but classified product → shelf suppressed
        url="https://shop.example/wilkinson-razor-p-123",
        query="what is the price and is it in stock?",
    )
    assert data["answer"] == "Price: 42.00 TRY. In stock."
    assert "options" not in data  # footer chrome never reaches the wire
    assert "refinement_axes" not in data  # sibling gate, same classification


@pytest.mark.asyncio
async def test_non_listing_ask_omits_options(monkeypatch: pytest.MonkeyPatch) -> None:
    # A page with no minable records AND a non-listing classification: doubly empty.
    data = await _ask_wire_classified(
        monkeypatch,
        body=b"<html><body><main><p>" + b"A plain article body. " * 40 + b"</p></main></body></html>",
        envelope={"answer": "A.", "structural_form": "article", "shape": "prose"},
        url="https://example.org/post",
        query="q?",
    )
    assert "options" not in data


@pytest.mark.asyncio
async def test_options_never_on_fetch_raw_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    # fetch_raw already returns the record block in content_md — the structured
    # options carrier is excluded from its wire.
    data = await _fetch_raw_wire(monkeypatch, body=_listing_html(6), url="https://shop.example/ara?q=crimp")
    assert "options" not in data
