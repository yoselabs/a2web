"""Site handler tests — match dispatch + JSON-to-markdown rendering."""

from __future__ import annotations

import json
from pathlib import Path

from a2web.handlers import HNHandler, RedditHandler, match_handler
from a2web.handlers.hn import _render_item
from a2web.handlers.reddit import _render_thread

_FIX = Path(__file__).parent / "fixtures"


def test_match_handler_returns_none_for_arbitrary_url() -> None:
    assert match_handler("https://example.com/post") is None


def test_match_handler_returns_reddit() -> None:
    handler = match_handler("https://www.reddit.com/r/x/comments/abc/title/")
    assert isinstance(handler, RedditHandler)


def test_match_handler_returns_hn() -> None:
    handler = match_handler("https://news.ycombinator.com/item?id=12345")
    assert isinstance(handler, HNHandler)


def test_reddit_matches_old_subdomain() -> None:
    assert RedditHandler().matches("https://old.reddit.com/r/x/comments/abc/")


def test_reddit_does_not_match_subreddit_listing() -> None:
    assert not RedditHandler().matches("https://www.reddit.com/r/x/")


def test_reddit_does_not_match_user_page() -> None:
    assert not RedditHandler().matches("https://www.reddit.com/user/somebody/")


def test_hn_matches_item_url() -> None:
    assert HNHandler().matches("https://news.ycombinator.com/item?id=12345")


def test_hn_does_not_match_front_page() -> None:
    assert not HNHandler().matches("https://news.ycombinator.com/")


def test_hn_does_not_match_user_page() -> None:
    assert not HNHandler().matches("https://news.ycombinator.com/user?id=denis")


def test_reddit_render_thread_includes_post_and_quoted_comments() -> None:
    payload = json.loads((_FIX / "reddit_thread.json").read_text())
    rendered = _render_thread(payload)

    assert rendered["title"] == "Best Local LLMs in April 2026"
    assert rendered["byline"] == "u/somebody"

    md = rendered["content_md"]
    assert md.startswith("# Best Local LLMs in April 2026")
    assert "Qwen3-32B is the surprise leader" in md
    # Top-level comment quoted with `>`
    assert "> Top-level comment with multiline" in md
    # Nested reply quoted with `>>`
    assert ">> Nested reply at depth 2." in md
    # Author byline rendered
    assert "— u/alice" in md
    assert "— u/bob" in md
    assert "— u/charlie" in md

    # 'more' stub is counted
    assert rendered["more_stubs"] == 17


def test_hn_render_item_includes_story_and_quoted_replies() -> None:
    payload = json.loads((_FIX / "hn_item.json").read_text())
    rendered = _render_item(payload)

    assert rendered["title"] == "Show HN: a2web — adaptive web fetching for AI agents"
    assert rendered["byline"] == "denis"

    md = rendered["content_md"]
    assert md.startswith("# Show HN: a2web")
    assert "https://example.org/a2web" in md
    # Top-level reply at depth 1
    assert "> Top-level comment from alice." in md
    # Nested reply at depth 2
    assert ">> The Reddit handler hits" in md
    # Bob's comment also depth 1
    assert "> What about anti-bot pages?" in md
    assert "— alice" in md
    assert "— bob" in md
    assert "— denis" in md
