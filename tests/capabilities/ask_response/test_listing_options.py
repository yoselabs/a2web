"""ask-retains-listing-options: rank-don't-skip.

`ask` keeps a ranked verdict in `answer` but stops deleting the field it ranked
over — a neutral, page-order `options` shelf rides the wire on a listing, absent
on non-listings, and never on the `fetch_raw` wire.
"""

from __future__ import annotations

import pytest
from record_mine import Record, RecordSet

from a2web.fetcher_response import _records_to_options
from tests.capabilities.ask_response.test_ask_response import _MINIMAL_HTML, _ask_wire
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


@pytest.mark.asyncio
async def test_listing_ask_carries_options(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=_listing_html(6),
        url="https://shop.example/ara?q=crimp&siralama=artanFiyat",
        query="which crimping tool is best?",
    )
    assert isinstance(data["options"], list)
    assert len(data["options"]) == 6  # every parsed record retained, none skipped
    for opt in data["options"]:
        assert "title" in opt


@pytest.mark.asyncio
async def test_non_listing_ask_omits_options(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/post", query="q?")
    assert "options" not in data


@pytest.mark.asyncio
async def test_options_never_on_fetch_raw_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    # fetch_raw already returns the record block in content_md — the structured
    # options carrier is excluded from its wire.
    data = await _fetch_raw_wire(monkeypatch, body=_listing_html(6), url="https://shop.example/ara?q=crimp")
    assert "options" not in data
