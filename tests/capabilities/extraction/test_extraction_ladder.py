"""The multi-source extraction-escalation ladder — routing and replace rules.

Covers the record-extraction rung: a server-rendered listing with no embedded
JSON reaches structural record extraction, a well-extracted article is never
clobbered, and detected records populate `next_links`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from a2web.fetcher import _run_extraction_escalation
from a2web.models import NextLink


@dataclass
class _FakeFc:
    content_md: str = ""
    final_url: str = ""
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)


# A server-rendered listing — 12 repeated record cards, no embedded JSON.
_LISTING_HTML = (
    "<html><body><div class='listing'>"
    + "".join(
        f"<article class='row'>"
        f"<h3><a href='/item/{i}'>Item number {i} title</a></h3>"
        f"<p>A description of item {i} explaining what it is about in some detail.</p>"
        f"</article>"
        for i in range(12)
    )
    + "</div></body></html>"
)

# An article page — high recall — that ALSO carries a small related-posts list.
_ARTICLE_TEXT = "This is a substantial article with real prose. " * 40
_ARTICLE_WITH_RELATED = (
    "<html><body>"
    f"<article>{_ARTICLE_TEXT}</article>"
    "<ul class='related'>"
    + "".join(f"<li><a href='/related/{i}'>Related post {i}</a></li>" for i in range(8))
    + "</ul></body></html>"
)


@pytest.mark.asyncio
async def test_server_rendered_listing_routes_to_record_extraction() -> None:
    """No embedded JSON → the ladder falls to the record-extraction source."""
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert "Listing (" in fc.content_md
    assert "Item number 0 title" in fc.content_md


@pytest.mark.asyncio
async def test_listing_populates_next_links() -> None:
    """Detected records become drilldown next_links candidates."""
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert len(fc.next_links_handler) == 12
    assert all(nl.kind == "drilldown" for nl in fc.next_links_handler)
    # primary link is the heading link, resolved against final_url
    assert fc.next_links_handler[0].url == "https://example.com/item/0"


@pytest.mark.asyncio
async def test_good_article_not_clobbered_by_record_cluster() -> None:
    """trafilatura captured the article (high recall) → ladder skipped; the
    related-posts cluster never replaces the article."""
    fc = _FakeFc(content_md=_ARTICLE_TEXT, final_url="https://example.com/post")
    await _run_extraction_escalation(fc, raw_html=_ARTICLE_WITH_RELATED)
    assert fc.content_md == _ARTICLE_TEXT
    assert fc.next_links_handler == []
