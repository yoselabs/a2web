"""Site handler tests — match dispatch + JSON-to-markdown rendering."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from purgatory import AsyncCircuitBreakerFactory

from a2web.handlers import HNHandler, RedditHandler, match_handler
from a2web.handlers.hn import _render_item
from a2web.handlers.reddit import _fetch_old_reddit, _render_thread, _to_old_reddit_url
from a2web.log.writer import LogWriter
from a2web.models import Verdict
from a2web.proxy.pool import ProxyPool
from a2web.settings import AppSettings
from a2web.state import AppState

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


# --------------------------------------------------------------------- #
# v0.3 Reddit fallback: old.reddit.com when .json fails or is empty
# --------------------------------------------------------------------- #


def _make_state() -> AppState:
    s = AppSettings()
    return AppState(
        settings=s,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=True),
        proxy_pool=ProxyPool(settings=s),
    )


def test_to_old_reddit_url_drops_json_and_query() -> None:
    """`<host>/r/X/comments/Y/title.json?...` → `old.reddit.com/r/X/comments/Y/title`."""
    out = _to_old_reddit_url(
        "https://www.reddit.com/r/programming/comments/abc/some_title.json?limit=500"
    )
    assert out == "https://old.reddit.com/r/programming/comments/abc/some_title"


def test_to_old_reddit_url_handles_no_json_suffix() -> None:
    """When the URL doesn't end with .json, just swap the host."""
    out = _to_old_reddit_url(
        "https://www.reddit.com/r/programming/comments/abc/some_title/"
    )
    assert out == "https://old.reddit.com/r/programming/comments/abc/some_title"


@pytest.mark.asyncio
async def test_old_reddit_fallback_returns_content_on_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v0.3: old.reddit fallback extracts via trafilatura on HTTP 200."""
    html = (
        "<!doctype html><html><body><article>"
        "<h1>The Future of Software Engineering</h1>"
        "<p>" + ("Substantive thread body. " * 80) + "</p>"
        "<div class='comment'><p>top reply</p></div>"
        "</article></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        # Should be called against old.reddit.com
        assert "old.reddit.com" in str(request.url)
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await _fetch_old_reddit(
        "https://www.reddit.com/r/programming/comments/abc/title/",
        state=_make_state(),
    )

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md  # non-empty


@pytest.mark.asyncio
async def test_old_reddit_fallback_returns_not_found_on_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When old.reddit also 404s, return not_found verdict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await _fetch_old_reddit(
        "https://www.reddit.com/r/x/comments/dead/", state=_make_state()
    )

    assert result.verdict == Verdict.not_found
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_json_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: .json 404 → tries old.reddit and returns its content."""
    html = (
        "<html><body><article>"
        "<h1>Recoverable thread</h1>"
        "<p>" + ("body " * 100) + "</p>"
        "</article></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if ".json" in url:
            return httpx.Response(404)
        # old.reddit fallback
        assert "old.reddit.com" in url
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    handler_obj = RedditHandler()
    result = await handler_obj.fetch(
        "https://www.reddit.com/r/x/comments/abc/title/", state=_make_state()
    )

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_empty_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: .json 200 but empty render → tries old.reddit."""
    html = (
        "<html><body><article>"
        "<h1>Quarantined-but-readable</h1>"
        "<p>" + ("body " * 100) + "</p>"
        "</article></body></html>"
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if ".json" in url:
            # Valid JSON but renders to empty content_md.
            return httpx.Response(200, json=[{}, {}])
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch(
        "https://www.reddit.com/r/x/comments/abc/title/", state=_make_state()
    )

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md
    # Two requests: .json then old.reddit
    assert len(calls) == 2
    assert ".json" in calls[0]
    assert "old.reddit.com" in calls[1]


@pytest.mark.asyncio
async def test_reddit_handler_skips_fallback_when_json_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When .json returns a renderable thread, old.reddit is NOT fetched."""
    payload = json.loads((_FIX / "reddit_thread.json").read_text())
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if ".json" in url:
            return httpx.Response(200, json=payload)
        return httpx.Response(404)  # would-be old.reddit; shouldn't be hit

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch(
        "https://www.reddit.com/r/x/comments/abc/title/", state=_make_state()
    )

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.title == "Best Local LLMs in April 2026"
    # Single request — old.reddit not touched.
    assert len(calls) == 1
    assert ".json" in calls[0]
