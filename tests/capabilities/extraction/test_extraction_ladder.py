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
from datetime import UTC, datetime

import pytest

from a2web.fetcher import _run_extraction_escalation
from a2web.fetcher.context import FetchInputs
from a2web.models import NextLink


@dataclass
class _FakeFc:
    content_md: str = ""
    final_url: str = ""
    #: §7.2 lifted the frozen preamble off `FetchContext`; the double carries the
    #: REAL `FetchInputs` rather than a shim, so it cannot drift from the shape
    #: the code under test actually reads.
    inputs: FetchInputs = field(
        default_factory=lambda: FetchInputs(
            started_at=datetime.now(UTC), start_perf=time.perf_counter(), profile_hash="x", bypass_cache=True
        )
    )
    next_links_handler: list[NextLink] = field(default_factory=list)
    # Mirrors `FetchContext`: the escalation installs a JSON-LD-derived record
    # set here when the DOM miner found none (ADR-0015 listing index).
    record_set: object | None = None
    record_count: int | None = None
    # Mirrors `FetchContext`: the ladder installs the page's own declared
    # subject entity here (ADR-0018 / declared_entity_v4).
    declared_entity: object | None = None


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
        f"<li class='comment'><h4><a href='/u/user{i}'>user{i}</a></h4><div class='ct'>{body}</div><ol class='comments'>{replies}</ol></li>"
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
async def test_listing_emits_drilldown_next_links() -> None:
    """A catalog row points ON-host at the item's own page: a `drilldown`.

    **Corrected 2026-08-01.** This asserted `source` for every record, and was
    named `test_listing_emits_source_next_links` — the miner hardcoded the
    aggregator vocabulary, so a shop listing announced that it was "discussing"
    the products it sells. `test_aggregator_record_emits_source_and_discussion`
    below is the other half and is unchanged: an off-host row IS a source.
    """
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert len(fc.next_links_handler) == 12
    assert all(nl.kind == "drilldown" for nl in fc.next_links_handler)
    assert all(nl.reason == "item page" for nl in fc.next_links_handler)
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
        "<ul class='related'>" + "".join(f"<li><a href='/related/{i}'>Related post {i}</a></li>" for i in range(8)) + "</ul></body></html>"
    )
    fc = _FakeFc(content_md=article_text, final_url="https://example.com/post")
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == article_text
    assert fc.next_links_handler == []


# --------------------------------------------------------------------- #
# A site handler's index outranks the generic miner's
# --------------------------------------------------------------------- #


def _handler_links() -> list[NextLink]:
    """What a site handler builds: real titles, site-specific reasons."""
    return [
        NextLink(
            anchor="Sample Efficiency in Repeated Reasoning",
            url="https://example.com/item/0",
            reason="I. Mirzaei, K. Cho",
            kind="drilldown",
        ),
    ]


@pytest.mark.asyncio
async def test_a_site_handlers_links_survive_the_extraction_ladder() -> None:
    """THE regression, measured on the wire before it was reproduced here.

    A pre-rendered tier runs this ladder too (see `_phase_extract`), and the
    install was unconditional — so the generic miner replaced whatever the site
    handler had built. The arXiv listing shipped `anchor="arXiv:2607.28618"`, a
    string identical to its own URL, and `reason="discussed page"`, while the
    handler's paper titles and author lists were computed and thrown away
    (bench 2026-08-01, `eval/runs/2026-08-01_011025/`).

    Same rule as `_compose_next_links` and the JSON-LD fallback: a later stage
    may ADD to a producer's index, never silently replace it. The handler knows
    the site; the miner is guessing from shape.
    """
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list", next_links_handler=_handler_links())
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)

    assert [nl.anchor for nl in fc.next_links_handler] == ["Sample Efficiency in Repeated Reasoning"]
    assert fc.next_links_handler[0].reason == "I. Mirzaei, K. Cho"


@pytest.mark.asyncio
async def test_the_miner_still_fills_when_the_handler_supplied_nothing() -> None:
    """Anti-vacuity: precedence must not become suppression.

    Most pages have no site handler at all. If the guard blocked the miner
    outright, `other_pages` would empty on every generic listing — the ADR-0015
    hole this ladder exists to close.
    """
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    assert len(fc.next_links_handler) == 12


@pytest.mark.asyncio
async def test_the_miner_would_otherwise_have_produced_a_different_index() -> None:
    """Non-vacuity for the precedence test: the two indexes must actually differ.

    If the miner produced nothing on `_LISTING_HTML`, the survival assertion
    above would hold for the wrong reason and keep holding after a revert.
    """
    fc = _FakeFc(content_md="Home Login", final_url="https://example.com/list")
    await _run_extraction_escalation(fc, raw_html=_LISTING_HTML)
    mined = {nl.anchor for nl in fc.next_links_handler}
    assert mined, "the miner produced no index — this fixture cannot witness precedence"
    assert "Sample Efficiency in Repeated Reasoning" not in mined
