"""The multi-source extraction-escalation ladder — depth-aware replace and
dual-link `next_links`.

The record-extraction rung runs unconditionally (no recall trigger). A flat
catalog replaces `content_md` on length and emits `source` / `discussion`
`next_links`; a threaded discussion replaces regardless of length and emits no
`next_links`.
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


# A flat catalog — 12 cards, each with a heading link only (the source).
_LISTING_HTML = (
    "<html><body><div class='listing'>"
    + "".join(
        "<article class='row'>"
        f"<h3><a href='/item/{i}'>Item number {i} title</a></h3>"
        f"<p>A description of item {i} explaining what it is about in some detail.</p>"
        "</article>"
        for i in range(12)
    )
    + "</div></body></html>"
)

# A flat aggregator — each story carries a heading link to the discussed page
# AND a same-host "N comments" anchor to the discussion thread.
_AGGREGATOR_HTML = (
    "<html><body><ol class='stories'>"
    + "".join(
        "<li class='story'>"
        f"<h2><a href='https://ext{i}.example.org/post'>External article {i} headline</a></h2>"
        f"<span class='meta'><a href='https://news.example.com/s/{i}'>{i + 2} comments</a></span>"
        "</li>"
        for i in range(6)
    )
    + "</ol></body></html>"
)


def _comment(i: int, body: str, replies: str = "") -> str:
    return (
        "<li class='comment'>"
        f"<h4><a href='/u/user{i}'>user{i}</a></h4>"
        f"<div class='ct'>{body}</div>"
        f"<ol class='comments'>{replies}</ol>"
        "</li>"
    )


# A threaded discussion — 3 top comments, each with one nested reply.
_THREAD_HTML = (
    "<html><body><ol class='comments'>"
    + _comment(
        0,
        "Top comment zero with a real sentence of discussion here.",
        _comment(10, "A reply to comment zero adding something more here."),
    )
    + _comment(
        1,
        "Top comment one offering an opinion at some length here today.",
        _comment(11, "A reply to comment one continuing the thread onward."),
    )
    + _comment(
        2,
        "Top comment two raising a separate point worth saying aloud.",
        _comment(12, "A reply to comment two wrapping up the discussion."),
    )
    + "</ol></body></html>"
)


@pytest.mark.asyncio
async def test_flat_catalog_replaces_on_length() -> None:
    """A flat catalog with no embedded JSON reaches the record rung and, when
    its render is longer than trafilatura's output, replaces content_md."""
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert fc.content_md.startswith("### Listing")
    assert "Item number 0 title" in fc.content_md


@pytest.mark.asyncio
async def test_listing_emits_source_next_links() -> None:
    """A catalog whose records carry only a heading link emits one `source`
    candidate per record."""
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert len(fc.next_links_handler) == 12
    assert all(nl.kind == "source" for nl in fc.next_links_handler)
    assert fc.next_links_handler[0].url == "https://example.com/item/0"


@pytest.mark.asyncio
async def test_aggregator_record_emits_source_and_discussion() -> None:
    """An aggregator record with a heading link AND a comment-count anchor
    emits both a `source` and a `discussion` candidate."""
    fc = _FakeFc(content_md="Home Login", final_url="https://news.example.com/")
    await _run_extraction_escalation(fc, raw_html=_AGGREGATOR_HTML)
    kinds = [nl.kind for nl in fc.next_links_handler]
    assert kinds.count("source") == 6
    assert kinds.count("discussion") == 6
    sources = {nl.url for nl in fc.next_links_handler if nl.kind == "source"}
    discussions = {nl.url for nl in fc.next_links_handler if nl.kind == "discussion"}
    assert "https://ext0.example.org/post" in sources
    assert "https://news.example.com/s/0" in discussions


@pytest.mark.asyncio
async def test_threaded_discussion_replaces_regardless_of_length() -> None:
    """A threaded record set replaces content_md even when trafilatura's
    output is far longer — trafilatura cannot represent threading."""
    long_wall = "flattened wall of comment text with no structure at all. " * 200
    fc = _FakeFc(content_md=long_wall, final_url="https://forum.example.com/t/1")
    await _run_extraction_escalation(fc, raw_html=_THREAD_HTML)
    assert fc.content_md.startswith("### Discussion")
    assert len(fc.content_md) < len(long_wall)


@pytest.mark.asyncio
async def test_threaded_discussion_emits_no_next_links() -> None:
    """A threaded record set is a conversation already inline — no drilldown."""
    fc = _FakeFc(content_md="x", final_url="https://forum.example.com/t/1")
    await _run_extraction_escalation(fc, raw_html=_THREAD_HTML)
    assert fc.content_md.startswith("### Discussion")
    assert fc.next_links_handler == []


@pytest.mark.asyncio
async def test_good_article_not_clobbered_by_record_cluster() -> None:
    """The ladder runs unconditionally — there is no recall trigger — but the
    record rung self-gates: the related-posts `<li>` cluster has an empty
    class token, the detector guards reject it, and the article stands."""
    article_text = "This is a substantial article with real prose. " * 40
    html = (
        "<html><body>"
        f"<article>{article_text}</article>"
        "<ul class='related'>"
        + "".join(f"<li><a href='/related/{i}'>Related post {i}</a></li>" for i in range(8))
        + "</ul></body></html>"
    )
    fc = _FakeFc(content_md=article_text, final_url="https://example.com/post")
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == article_text
    assert fc.next_links_handler == []
