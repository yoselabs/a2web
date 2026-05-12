"""Site handler tests — match dispatch + JSON-to-markdown rendering."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from a2web.handlers import HNHandler, RedditHandler, TwitterHandler, match_handler
from a2web.handlers.hn import _render_item
from a2web.handlers.reddit import _fetch_old_reddit, _render_thread, _to_old_reddit_url
from a2web.models import Verdict
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
    from a2web.state import build_state

    return build_state(settings=AppSettings())


def test_to_old_reddit_url_drops_json_and_query() -> None:
    """`<host>/r/X/comments/Y/title.json?...` → `old.reddit.com/r/X/comments/Y/title`."""
    out = _to_old_reddit_url("https://www.reddit.com/r/programming/comments/abc/some_title.json?limit=500")
    assert out == "https://old.reddit.com/r/programming/comments/abc/some_title"


def test_to_old_reddit_url_handles_no_json_suffix() -> None:
    """When the URL doesn't end with .json, just swap the host."""
    out = _to_old_reddit_url("https://www.reddit.com/r/programming/comments/abc/some_title/")
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

    result = await _fetch_old_reddit("https://www.reddit.com/r/x/comments/dead/", state=_make_state())

    assert result.verdict == Verdict.not_found
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_json_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: .json 404 → tries old.reddit and returns its content."""
    html = "<html><body><article><h1>Recoverable thread</h1><p>" + ("body " * 100) + "</p></article></body></html>"

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
    result = await handler_obj.fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_empty_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: .json 200 but empty render → tries old.reddit."""
    html = "<html><body><article><h1>Quarantined-but-readable</h1><p>" + ("body " * 100) + "</p></article></body></html>"
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

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

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

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.title == "Best Local LLMs in April 2026"
    # Single request — old.reddit not touched.
    assert len(calls) == 1
    assert ".json" in calls[0]


# --------------------------------------------------------------------- #
# v0.3 Twitter / X handler via Nitter rotation
# --------------------------------------------------------------------- #


def _make_state_with_nitter(*instances: str) -> AppState:
    from a2web.state import build_state

    s = AppSettings(nitter_instances=list(instances))
    return build_state(settings=s)


def test_twitter_handler_matches_x_status_urls() -> None:
    h = TwitterHandler()
    assert h.matches("https://x.com/karpathy/status/1759031023815639423")
    assert h.matches("https://www.x.com/karpathy/status/1759031023815639423")
    assert h.matches("https://twitter.com/karpathy/status/1759031023815639423")
    assert h.matches("https://twitter.com/karpathy/status/1759031023815639423/photo/1")


def test_twitter_handler_does_not_match_profile_or_home() -> None:
    h = TwitterHandler()
    assert not h.matches("https://x.com/karpathy")
    assert not h.matches("https://x.com/karpathy/")
    assert not h.matches("https://x.com/home")
    assert not h.matches("https://x.com/")


def test_twitter_handler_does_not_match_other_hosts() -> None:
    h = TwitterHandler()
    assert not h.matches("https://example.com/karpathy/status/123")
    assert not h.matches("https://nitter.net/karpathy/status/123")


@pytest.mark.asyncio
async def test_twitter_handler_no_match_when_no_instances_configured() -> None:
    """Empty nitter_instances → fetch returns no_match=True silently."""
    state = _make_state_with_nitter()  # no instances
    result = await TwitterHandler().fetch("https://x.com/karpathy/status/1759031023815639423", state=state)
    assert result.no_match is True


@pytest.mark.asyncio
async def test_twitter_handler_returns_content_from_first_working_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One configured Nitter instance returning 200 → handler extracts content."""
    tweet_html = (
        "<html><body><article>"
        "<h1>karpathy</h1>"
        "<div class='tweet-content'>" + ("substantive tweet body. " * 60) + "</div>"
        "</article></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "nitter.example.com" in str(request.url)
        return httpx.Response(200, text=tweet_html)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    state = _make_state_with_nitter("https://nitter.example.com")
    result = await TwitterHandler().fetch("https://x.com/karpathy/status/1759031023815639423", state=state)

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert "substantive" in result.pre_rendered.content_md


@pytest.mark.asyncio
async def test_twitter_handler_rotates_past_failing_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First instance times out / 5xx → handler tries the next one."""
    tweet_html = "<html><body><article><div>" + ("recovered body. " * 60) + "</div></article></body></html>"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        # First instance always fails (5xx), second succeeds.
        if "fail.example.com" in url:
            return httpx.Response(503)
        return httpx.Response(200, text=tweet_html)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    # Disable shuffle for deterministic order — patch random.shuffle to no-op.
    monkeypatch.setattr("a2web.handlers.twitter.random.shuffle", lambda _: None)

    state = _make_state_with_nitter("https://fail.example.com", "https://ok.example.com")
    result = await TwitterHandler().fetch("https://x.com/karpathy/status/123", state=state)

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    # Both instances were probed in order.
    assert any("fail.example.com" in u for u in seen)
    assert any("ok.example.com" in u for u in seen)


@pytest.mark.asyncio
async def test_twitter_handler_returns_empty_when_all_instances_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All instances 5xx → handler returns the last verdict (connection_error)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    state = _make_state_with_nitter("https://a.example.com", "https://b.example.com")
    result = await TwitterHandler().fetch("https://x.com/karpathy/status/123", state=state)

    assert result.verdict == Verdict.connection_error
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_match_handler_includes_twitter() -> None:
    """The dispatcher returns TwitterHandler for x.com status URLs."""
    handler = match_handler("https://x.com/karpathy/status/1759031023815639423")
    assert isinstance(handler, TwitterHandler)


# --------------------------------------------------------------------- #
# v0.6 Reddit: permalink focus + crosspost + archive escalation + short URL
# --------------------------------------------------------------------- #


def test_reddit_matches_short_url() -> None:
    """redd.it/<id> is claimed by the handler for HEAD-resolution."""
    assert RedditHandler().matches("https://redd.it/abc123")


def test_reddit_matches_np_subdomain() -> None:
    """np.reddit.com (no-participation) URLs are recognized."""
    assert RedditHandler().matches("https://np.reddit.com/r/x/comments/abc/title/")


def test_reddit_permalink_detection() -> None:
    """Trailing base36 segment after slug is the focused comment id."""
    from a2web.handlers.reddit import _detect_permalink

    # Permalink — slug + comment id
    assert _detect_permalink("https://www.reddit.com/r/x/comments/abc/some_title/k7x9z2/") == "k7x9z2"
    # Bare thread — slug only, no permalink
    assert _detect_permalink("https://www.reddit.com/r/x/comments/abc/some_title/") is None
    # Slug-only with no trailing slash
    assert _detect_permalink("https://www.reddit.com/r/x/comments/abc/some_title") is None
    # Underscore in trailing segment → it's a slug, not a comment id
    assert _detect_permalink("https://www.reddit.com/r/x/comments/abc/slug/another_slug/") is None


def test_reddit_render_permalink_includes_target_and_ancestors() -> None:
    """Focused render shows the target comment with ancestor context."""
    from a2web.handlers.reddit import _render_thread

    payload = json.loads((_FIX / "reddit_permalink.json").read_text())
    rendered = _render_thread(payload, target_comment="target99")

    md = rendered["content_md"]
    assert "Focused comment" in md
    assert "🎯 Focused comment by u/charlie" in md
    assert "This is the focused target comment." in md
    # Ancestor block-quoted with context label.
    assert "Context — ancestors of the focused comment" in md
    assert "Top-level ancestor comment." in md
    assert "Mid-level ancestor." in md
    # Reply to the target is included.
    assert "Reply to the focused comment." in md


def test_reddit_render_permalink_falls_back_when_target_missing() -> None:
    """If the target id isn't in the tree, fall back to full thread render."""
    from a2web.handlers.reddit import _render_thread

    payload = json.loads((_FIX / "reddit_thread.json").read_text())
    rendered = _render_thread(payload, target_comment="nonexistent")

    md = rendered["content_md"]
    # Standard "## Comments" section instead of focused view.
    assert "## Comments" in md
    assert "Focused comment" not in md


def test_reddit_render_crosspost_includes_source_annotation() -> None:
    """Posts with crosspost_parent_list get a source annotation line."""
    from a2web.handlers.reddit import _render_thread

    payload = json.loads((_FIX / "reddit_crosspost.json").read_text())
    rendered = _render_thread(payload)

    md = rendered["content_md"]
    assert "🔁 Crossposted from" in md
    assert "r/MachineLearning" in md
    assert "u/original_author" in md
    # Original title surfaced in the annotation.
    assert "How agent fetchers handle paywalls" in md


def test_reddit_render_removed_post_marks_body() -> None:
    """selftext == '[removed]' is replaced with a visible marker."""
    from a2web.handlers.reddit import _render_thread

    payload = json.loads((_FIX / "reddit_removed.json").read_text())
    rendered = _render_thread(payload)

    md = rendered["content_md"]
    assert "_[post body removed]_" in md
    # Title still rendered.
    assert "An interesting question" in md


@pytest.mark.asyncio
async def test_reddit_handler_signals_archive_on_404_when_old_reddit_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When .json 404 AND old.reddit 404, return not_found with archive hint.

    The playbook reads `verdict=not_found` on a reddit URL and dispatches
    the archive tier next.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch(
        "https://www.reddit.com/r/x/comments/dead/title/", state=_make_state()
    )

    assert result.verdict == Verdict.not_found
    assert result.pre_rendered is None
    assert result.operator_hint is not None
    assert result.operator_hint.code == "reddit_deleted_try_archive"


@pytest.mark.asyncio
async def test_reddit_handler_signals_archive_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """403 (quarantined/NSFW/private) skips old.reddit and asks for archive."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch(
        "https://www.reddit.com/r/x/comments/abc/title/", state=_make_state()
    )

    assert result.verdict == Verdict.not_found
    assert result.operator_hint is not None
    assert result.operator_hint.code == "reddit_forbidden_try_archive"


@pytest.mark.asyncio
async def test_reddit_handler_resolves_short_url_then_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redd.it/<id> → HEAD-resolved (via 301) → recursed → renders the thread."""
    payload = json.loads((_FIX / "reddit_thread.json").read_text())
    resolved_url = "https://www.reddit.com/r/x/comments/abc/some_title/"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "HEAD" and "redd.it" in url:
            return httpx.Response(301, headers={"location": resolved_url})
        if request.method == "HEAD":
            return httpx.Response(200)
        if ".json" in url:
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch("https://redd.it/abc", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.title == "Best Local LLMs in April 2026"


@pytest.mark.asyncio
async def test_reddit_handler_short_url_no_match_for_non_thread_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If redd.it resolves to a non-thread URL, return no_match=True."""
    resolved_url = "https://www.reddit.com/r/x/"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "HEAD" and "redd.it" in url:
            return httpx.Response(301, headers={"location": resolved_url})
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch("https://redd.it/abc", state=_make_state())

    assert result.no_match is True
    assert result.final_url == resolved_url


def test_playbook_escalates_reddit_not_found_to_archive() -> None:
    """next_action_after_tier: reddit URL + not_found → RetryViaArchive."""
    from a2web.actions import RetryViaArchive, next_action_after_tier
    from a2web.tiers import TierResult

    tr = TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url="https://www.reddit.com/r/x/comments/dead/",
        verdict=Verdict.not_found,
    )
    action = next_action_after_tier(tr, "https://www.reddit.com/r/x/comments/dead/")
    assert isinstance(action, RetryViaArchive)
    assert action.url == "https://www.reddit.com/r/x/comments/dead/"


def test_playbook_does_not_escalate_not_found_on_other_hosts() -> None:
    """The reddit not_found rule does not fire for non-reddit hosts."""
    from a2web.actions import next_action_after_tier
    from a2web.tiers import TierResult

    tr = TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url="https://example.com/page",
        verdict=Verdict.not_found,
    )
    action = next_action_after_tier(tr, "https://example.com/page")
    assert action is None
