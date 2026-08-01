"""A record's heading link is classified by where it points, not by a constant.

`_records_to_next_links` hardcoded `("source", "discussed page")` for every
record's heading link. That is the AGGREGATOR vocabulary — an HN or Lobsters row
points OFF-host at an article the page discusses.

The same miner runs on catalogs, where a row points ON-host at the item's own
detail page. Labelling that `source` asserts the page is discussing something it
is in fact selling, and `reason="discussed page"` says so in prose. Every
commerce listing carried it, and the JSON-LD `ItemList` path (added 2026-08-01)
routes straight into this function, so every `ItemList` catalog inherited it.

Same class as the `other_pages[].kind` correction earlier the same day: a
producer asserting a property of its own output that is false. ADR-0014 requires
every emitted URL be traceable to the page; nothing required the LABEL on it to
be true, which is how this survived.

Off-host vs on-host is the discriminator because it is what actually separates
the two shapes — an aggregator row exists to leave the host, a catalog row to go
deeper into it.
"""

from __future__ import annotations

import pytest
from record_mine import Record, RecordSet

from a2web.fetcher import _records_to_next_links

_PAGE = "https://shop.example.com/laptops"


def _one(url: str, *, page_url: str = _PAGE) -> RecordSet:
    return RecordSet(
        records=(
            Record(
                text="ProBook 450 — 899 USD",
                links=(),
                heading_text="ProBook 450",
                heading_link=("ProBook 450", url),
                depth=0,
                markdown="",
            ),
        ),
        container="ul",
        child_signature="li",
        max_depth=0,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://shop.example.com/p/probook-450",  # same host
        "https://www.shop.example.com/p/probook-450",  # www. variant of the same site
        "/p/probook-450",  # relative — cannot leave the host
    ],
)
def test_an_on_host_row_is_a_drilldown(url: str) -> None:
    """THE regression. Pre-fix every one of these said `source · discussed page`."""
    (link,) = _records_to_next_links(_one(url), page_url=_PAGE)
    assert link.kind == "drilldown"
    assert link.reason == "item page"


def test_an_off_host_row_is_still_a_source() -> None:
    """Anti-vacuity: the fix must not relabel everything `drilldown`.

    An aggregator row pointing away at the article it discusses is precisely
    what `source` is for, and collapsing the distinction would lose the one
    signal the field carries.
    """
    (link,) = _records_to_next_links(_one("https://blog.other.com/review"), page_url=_PAGE)
    assert link.kind == "source"
    assert link.reason == "discussed page"


def test_the_two_shapes_are_distinguished_on_the_same_page() -> None:
    """The discriminator is per record, not per page.

    A catalog that cites an external review alongside its own item pages must
    label each row for what it is — deciding once per page would be the same
    constant with more steps.
    """
    records = tuple(
        Record(
            text=f"row {i}",
            links=(),
            heading_text=f"row {i}",
            heading_link=(f"row {i}", url),
            depth=0,
            markdown="",
        )
        for i, url in enumerate(["https://shop.example.com/p/a", "https://reviews.elsewhere.io/a", "https://shop.example.com/p/b"])
    )
    record_set = RecordSet(records=records, container="ul", child_signature="li", max_depth=0)
    kinds = [nl.kind for nl in _records_to_next_links(record_set, page_url=_PAGE)]
    assert kinds == ["drilldown", "source", "drilldown"]
