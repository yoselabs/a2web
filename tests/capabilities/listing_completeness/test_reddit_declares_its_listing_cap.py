"""A Reddit listing longer than the render cap says so instead of going quiet.

`_post_entries` capped at 25 with the comment "(feed page size)" — which is what
Reddit normally returns, so the cap looked inert. But it is applied AFTER
filtering the feed's entries, so a feed handing back more than 25 renderable
posts lost the tail with nothing on the wire and nothing in the body.

That is the ADR-0015 harm on the sufficiency axis: `query` withholds the body,
so a caller reading a distilled answer cannot tell "the listing has 25 posts"
from "a2web rendered the first 25 of 60".

Reddit's Atom feed reports no total, so unlike `hn`'s `nbHits` there is no
source-stated figure to declare against — the note says "of what we received",
which is a floor on the shortfall rather than its true size. A floor is worth
saying; silence is not. Sibling of `test_hn_declares_the_source_total.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from a2web.handlers.reddit import (
    _LISTING_CAP,
    _AtomEntry,
    _AtomFeed,
    _render_listing_atom,
    _render_search_atom,
    _RenderResult,
)


def _feed(*, posts: int) -> _AtomFeed:
    """An Atom feed carrying `posts` renderable t3 entries."""
    now = time.time()
    entries = [
        _AtomEntry(
            kind="t3",
            reddit_id=f"t3_{i}",
            title=f"Post number {i}",
            author=f"user{i}",
            link=f"https://www.reddit.com/r/test/comments/{i}/post_number_{i}/",
            epoch=now - 3600,
            content_html=None,
        )
        for i in range(posts)
    ]
    return _AtomFeed(title="r/test", subtitle=None, entries=entries)


_RENDERERS = (
    pytest.param(lambda feed: _render_listing_atom(feed, subreddit="test", sort="hot", time_window=""), id="listing"),
    pytest.param(lambda feed: _render_search_atom(feed, query="anything"), id="search"),
)


@pytest.mark.parametrize("render", _RENDERERS)
def test_an_over_cap_feed_declares_the_partial_view(render: Callable[[_AtomFeed], _RenderResult]) -> None:
    """THE regression: pre-fix this rendered 25 of 60 in silence."""
    over = _LISTING_CAP * 2 + 10
    body = render(_feed(posts=over)).content_md

    assert f"{_LISTING_CAP} of {over}" in body, f"no partial-view declaration in:\n{body[:400]}"
    assert "partial view" in body


@pytest.mark.parametrize("render", _RENDERERS)
def test_a_feed_within_the_cap_stays_silent(render: Callable[[_AtomFeed], _RenderResult]) -> None:
    """Anti-vacuity: a note on every listing is a note on none of them."""
    body = render(_feed(posts=_LISTING_CAP - 5)).content_md
    assert "partial view" not in body


@pytest.mark.parametrize("render", _RENDERERS)
def test_an_exactly_full_page_stays_silent(render: Callable[[_AtomFeed], _RenderResult]) -> None:
    """The boundary. 25 of 25 is not news, and claiming it would be false."""
    body = render(_feed(posts=_LISTING_CAP)).content_md
    assert "partial view" not in body


@pytest.mark.parametrize("render", _RENDERERS)
def test_the_declared_count_matches_what_was_rendered(render: Callable[[_AtomFeed], _RenderResult]) -> None:
    """Anti-drift: the note and the body must not tell different stories.

    The same failure the arXiv handler was fixed for — prose and wire agreeing is
    the whole point of declaring, and a note quoting a number the body does not
    show is worse than no note.
    """
    body = render(_feed(posts=_LISTING_CAP * 3)).content_md
    assert body.count("- **Post number ") == _LISTING_CAP
