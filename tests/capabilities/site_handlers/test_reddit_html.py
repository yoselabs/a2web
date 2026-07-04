"""Unit tests for old.reddit URL normalization + flat-HTML parsing.

Covers `handlers/_reddit_html.py`: the normalization table for every Reddit
URL shape, the selectolax parser against a captured old.reddit fixture
(structured scored/nested comments + the comment-total oracle), and the
markdown render.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.handlers import _reddit_html as rh

_FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "reddit" / "oldreddit_thread.html"


# --------------------------------------------------------------------- #
# normalize()
# --------------------------------------------------------------------- #

_OLD_THREAD = "https://old.reddit.com/r/science/comments/abc123/why_pushups/?limit=500&sort=top"


@pytest.mark.parametrize(
    ("url", "channel", "expected"),
    [
        # new-reddit thread → old.reddit ?limit=500&sort=top
        ("https://www.reddit.com/r/science/comments/abc123/why_pushups/", "thread", _OLD_THREAD),
        # bare host, no slug
        ("https://reddit.com/r/science/comments/abc123/", "thread", "https://old.reddit.com/r/science/comments/abc123/?limit=500&sort=top"),
        # np. host
        ("https://np.reddit.com/r/science/comments/abc123/why_pushups/", "thread", _OLD_THREAD),
        # already old.reddit
        ("https://old.reddit.com/r/science/comments/abc123/why_pushups/", "thread", _OLD_THREAD),
        # .json suffix stripped, never re-emitted
        ("https://www.reddit.com/r/science/comments/abc123/why_pushups/.json", "thread", _OLD_THREAD),
        # .rss suffix stripped
        ("https://www.reddit.com/r/science/comments/abc123/why_pushups/.rss", "thread", _OLD_THREAD),
        # focused permalink → whole-thread old.reddit
        ("https://www.reddit.com/r/science/comments/abc123/why_pushups/c0comment/", "thread", _OLD_THREAD),
    ],
)
def test_normalize_thread_shapes(url: str, channel: str, expected: str) -> None:
    got_channel, got_url = rh.normalize(url)
    assert got_channel == channel
    assert got_url == expected
    assert ".json" not in got_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.reddit.com/r/gravelcycling/",
        "https://www.reddit.com/r/gravelcycling/top/",
        "https://old.reddit.com/r/science/search/?q=pushups",
    ],
)
def test_normalize_listing_stays_new_reddit(url: str) -> None:
    channel, got = rh.normalize(url)
    assert channel == "listing"
    assert got.startswith("https://www.reddit.com/")
    assert ".json" not in got


def test_normalize_listing_preserves_query() -> None:
    _, got = rh.normalize("https://old.reddit.com/r/science/search/?q=pushups&sort=top")
    assert "q=pushups" in got


# --------------------------------------------------------------------- #
# parse_thread()
# --------------------------------------------------------------------- #


def _thread() -> rh.RedditThread:
    thread = rh.parse_thread(_FIXTURE.read_text())
    assert thread is not None
    return thread


def test_parse_extracts_post_header_and_oracle() -> None:
    thread = _thread()
    assert thread.title == "Why are pushups so effective?"
    assert thread.author == "fitnerd"
    assert thread.subreddit == "science"
    assert thread.score == 1420
    assert "Compound movement" in thread.body_md
    # The authoritative oracle read off the `458 comments` bylink.
    assert thread.comment_total == 458


def test_parse_yields_scored_nested_comments() -> None:
    thread = _thread()
    # Two body-bearing comments (alice top-level, bob nested); the `more
    # comments` stub is skipped (no body).
    bodies = {c.author: c for c in thread.comments}
    assert bodies["alice"].score == 312
    assert bodies["alice"].depth == 0
    assert bodies["bob"].score == 87
    assert bodies["bob"].depth == 1
    assert "Progressive overload" in bodies["alice"].body_md


def test_parse_score_hidden_is_none_not_zero() -> None:
    thread = _thread()
    # The third comment has a deleted author + hidden score.
    hidden = next(c for c in thread.comments if "Deleted user reply" in c.body_md)
    assert hidden.score is None
    assert hidden.author == "[deleted]"


def test_parse_more_comments_stub_skipped() -> None:
    thread = _thread()
    assert all("load more comments" not in c.body_md for c in thread.comments)
    assert len(thread.comments) == 3  # alice, bob, deleted — not the stub


def test_parse_returns_none_on_non_thread_html() -> None:
    assert rh.parse_thread("<html><body><p>not a thread</p></body></html>") is None


# --------------------------------------------------------------------- #
# render_markdown()
# --------------------------------------------------------------------- #


def test_render_shows_oracle_gap_and_nesting() -> None:
    md = rh.render_markdown(_thread())
    assert "# Why are pushups so effective?" in md
    assert "Comments (3 of 458)" in md  # honest "top-N of M"
    assert "u/alice (312 points)" in md
    assert "> > Add a weight vest." in md  # bob is nested (depth 1 → double blockquote)
