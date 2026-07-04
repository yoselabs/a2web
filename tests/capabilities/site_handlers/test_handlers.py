"""Site handler tests — match dispatch + JSON-to-markdown rendering."""

from __future__ import annotations

import json
from typing import Any

import pytest

from a2web.handlers import HNHandler, RedditHandler, TwitterHandler, match_handler
from a2web.handlers.hn import _render_item
from a2web.handlers.reddit import _fetch_old_reddit, _to_old_reddit_url
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR
_RSS = FIXTURES_DIR / "reddit"


def _rss_bytes(name: str) -> bytes:
    return (_RSS / name).read_bytes()


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


def test_reddit_matches_subreddit_listing() -> None:
    """v0.7: bare subreddit + sorted listings (top/hot/new/...) are claimed."""
    assert RedditHandler().matches("https://www.reddit.com/r/x/")
    assert RedditHandler().matches("https://www.reddit.com/r/x/top/?t=year")
    assert RedditHandler().matches("https://www.reddit.com/r/x/hot/")
    assert RedditHandler().matches("https://www.reddit.com/r/x/new")


def test_reddit_does_not_match_user_page() -> None:
    assert not RedditHandler().matches("https://www.reddit.com/user/somebody/")


def test_reddit_matches_subreddit_search() -> None:
    """v0.7: subreddit-scoped search URLs are claimed by the handler."""
    assert RedditHandler().matches("https://www.reddit.com/r/projectors/search/?q=Wanbo+Mozart+1+Pro&restrict_sr=on")


def test_reddit_matches_unscoped_search() -> None:
    """v0.7: site-wide `/search/?q=...` is also claimed."""
    assert RedditHandler().matches("https://www.reddit.com/search/?q=projector")


# --------------------------------------------------------------------- #
# RSS (Atom) projection — search / listing / thread render from live feeds
# --------------------------------------------------------------------- #

_EMPTY_ATOM = b'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>empty</title></feed>'


def test_reddit_to_rss_url_projects_every_shape() -> None:
    """`.json`-free reddit URLs rewrite to their keyless `.rss` equivalent."""
    from a2web.handlers.reddit import _to_rss_url

    assert (
        _to_rss_url("https://www.reddit.com/r/gravelcycling/search/?q=bell&restrict_sr=1&sort=top", "search")
        == "https://www.reddit.com/r/gravelcycling/search.rss?q=bell&restrict_sr=1&sort=top"
    )
    assert _to_rss_url("https://www.reddit.com/r/gravelcycling/top/?t=year", "listing") == "https://www.reddit.com/r/gravelcycling/top.rss?t=year"
    # Bare / hot / best all map to the default feed (verified live: the bare
    # `.rss` feed IS the hot feed).
    assert _to_rss_url("https://www.reddit.com/r/gravelcycling/", "listing") == "https://www.reddit.com/r/gravelcycling/.rss"
    assert _to_rss_url("https://www.reddit.com/r/gravelcycling/hot/", "listing") == "https://www.reddit.com/r/gravelcycling/.rss"
    assert (
        _to_rss_url("https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/", "comments")
        == "https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/.rss"
    )


def test_reddit_render_search_atom_produces_list() -> None:
    """`_render_search_atom` emits a terse markdown list from a real search feed."""
    from a2web.handlers.reddit import _parse_atom, _render_search_atom

    rendered = _render_search_atom(_parse_atom(_rss_bytes("search.rss")), query="bell")
    assert rendered.is_empty is False
    md = rendered.content_md
    assert md.startswith("# Search: bell")
    assert "## Results (25)" in md
    assert "New bike day" in md
    assert "u/aspiring-housewife-" in md
    assert "https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/" in md
    # RSS carries no score / comment count — the meta line must never fabricate one.
    assert "score" not in md
    assert "comments)" not in md


def test_reddit_render_listing_atom_produces_list_and_next_links() -> None:
    """`_render_listing_atom` renders posts + drill-down next_links from a real feed."""
    from a2web.handlers.reddit import _parse_atom, _render_listing_atom

    rendered = _render_listing_atom(_parse_atom(_rss_bytes("listing.rss")), subreddit="gravelcycling", sort="top", time_window="year")
    assert rendered.is_empty is False
    md = rendered.content_md
    assert md.startswith("# r/gravelcycling · top · year")
    assert "## Posts (25)" in md
    # next_links capped at 10, drill-down into the thread permalinks.
    assert len(rendered.next_links) == 10
    assert rendered.next_links[0].kind == "drilldown"
    assert rendered.next_links[0].url.startswith("https://www.reddit.com/r/gravelcycling/comments/")
    assert rendered.next_links[0].anchor


def test_reddit_render_listing_atom_omits_time_window_for_non_top() -> None:
    """Hot/new don't take `?t=`; the suffix is omitted from the title."""
    from a2web.handlers.reddit import _parse_atom, _render_listing_atom

    rendered = _render_listing_atom(_parse_atom(_rss_bytes("listing.rss")), subreddit="x", sort="hot", time_window="year")
    assert rendered.content_md.startswith("# r/x · hot\n")


def test_reddit_render_search_atom_empty_feed_is_empty() -> None:
    """Zero entries → `is_empty=True` so the orchestrator surfaces not_found."""
    from a2web.handlers.reddit import _parse_atom, _render_search_atom

    rendered = _render_search_atom(_parse_atom(_EMPTY_ATOM), query="nothing-matches-here")
    assert rendered.is_empty is True
    assert rendered.content_md == ""


def test_reddit_human_age_compact() -> None:
    from a2web.handlers.reddit import human_age

    assert human_age(0) == "0s"
    assert human_age(45) == "45s"
    assert human_age(120) == "2m"
    assert human_age(7200) == "2h"
    assert human_age(86400 * 3) == "3d"
    assert human_age(86400 * 365 * 2) == "2y"


def test_hn_matches_item_url() -> None:
    assert HNHandler().matches("https://news.ycombinator.com/item?id=12345")


def test_hn_matches_front_page() -> None:
    """v0.7 link-discovery: HN handler matches `/` and `/news` to populate next_links."""
    assert HNHandler().matches("https://news.ycombinator.com/")
    assert HNHandler().matches("https://news.ycombinator.com/news")


def test_hn_front_page_candidates_external_and_text_only() -> None:
    """External-URL stories drill into external URL; text-only stories drill into the discussion page."""
    from a2web.handlers.hn import _front_page_candidates

    payload = {
        "hits": [
            {"title": "External story", "objectID": "111", "url": "https://example.com/article", "points": 200, "num_comments": 80},
            {"title": "Ask HN: thoughts?", "objectID": "222", "url": None, "points": 50, "num_comments": 30},
        ],
    }
    cands = _front_page_candidates(payload)
    assert len(cands) == 2
    assert cands[0].url == "https://example.com/article"
    assert cands[0].kind == "drilldown"
    assert cands[0].reason == "200 points, 80 comments"
    assert cands[1].url == "https://news.ycombinator.com/item?id=222"
    assert cands[1].anchor == "Ask HN: thoughts?"


def test_hn_front_page_candidates_capped_at_10() -> None:
    """Front page with 15 hits → exactly 10 candidates."""
    from a2web.handlers.hn import _front_page_candidates

    payload = {
        "hits": [
            {"title": f"Story {i}", "objectID": str(i), "url": f"https://e.com/{i}", "points": 100 - i, "num_comments": 5}
            for i in range(15)
        ],
    }
    assert len(_front_page_candidates(payload)) == 10


def test_hn_does_not_match_user_page() -> None:
    assert not HNHandler().matches("https://news.ycombinator.com/user?id=denis")


def test_reddit_render_thread_atom_includes_post_and_flat_comment_sample() -> None:
    """`_render_thread_atom` renders the OP + a FLAT, sample-labelled comment list."""
    from a2web.handlers.reddit import _parse_atom, _render_thread_atom

    rendered = _render_thread_atom(_parse_atom(_rss_bytes("thread.rss")))

    assert rendered.title == "New bike day"
    assert rendered.byline == "u/aspiring-housewife-"

    md = rendered.content_md
    assert md.startswith("# New bike day")
    assert "in r/gravelcycling" in md
    # OP body (md-div extracted; thumbnail table + SC markers stripped).
    assert "Ribble Allgrit Ti" in md
    assert "SC_OFF" not in md
    # Comments come back flat and are explicitly labelled a sample — never
    # implied complete (never-silently-miss / honest-degradation contract).
    assert "## Comments (sample of" in md
    assert "not scored, not ranked, not complete" in md
    assert "— u/Newyawker2022" in md
    # Flat: no nested `>>` quoting (RSS has no comment tree).
    assert ">>" not in md
    # Thread render carries no next_links (no drill-down layer).
    assert rendered.next_links == []


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
    from tests.conftest import make_default_state

    return make_default_state(settings=AppSettings())


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

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        # Should be called against old.reddit.com
        assert "old.reddit.com" in url
        return FakeCurlResp(200, text=html)

    patch_curl_session(monkeypatch, handler)

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

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(404)

    patch_curl_session(monkeypatch, handler)

    result = await _fetch_old_reddit("https://www.reddit.com/r/x/comments/dead/", state=_make_state())

    assert result.verdict == Verdict.not_found
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_rss_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: thread .rss 404 → tries old.reddit and returns its content."""
    html = "<html><body><article><h1>Recoverable thread</h1><p>" + ("body " * 100) + "</p></article></body></html>"

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if ".rss" in url:
            return FakeCurlResp(404)
        # old.reddit fallback
        assert "old.reddit.com" in url
        return FakeCurlResp(200, text=html)

    patch_curl_session(monkeypatch, handler)

    handler_obj = RedditHandler()
    result = await handler_obj.fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md


@pytest.mark.asyncio
async def test_reddit_handler_falls_back_on_empty_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RedditHandler: thread .rss 200 but empty render → tries old.reddit."""
    html = "<html><body><article><h1>Quarantined-but-readable</h1><p>" + ("body " * 100) + "</p></article></body></html>"
    calls: list[str] = []

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        calls.append(url)
        if ".rss" in url:
            # Valid Atom but renders to empty content_md (no entries).
            return FakeCurlResp(200, body=_EMPTY_ATOM, content_type="application/atom+xml")
        return FakeCurlResp(200, text=html)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md
    # Two requests: .rss then old.reddit
    assert len(calls) == 2
    assert ".rss" in calls[0]
    assert "old.reddit.com" in calls[1]


@pytest.mark.asyncio
async def test_reddit_handler_skips_fallback_when_rss_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When thread .rss returns a renderable feed, old.reddit is NOT fetched."""
    calls: list[str] = []

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        calls.append(url)
        if ".rss" in url:
            return FakeCurlResp(200, body=_rss_bytes("thread.rss"), content_type="application/atom+xml")
        return FakeCurlResp(404)  # would-be old.reddit; shouldn't be hit

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.title == "New bike day"
    # Single request — old.reddit not touched.
    assert len(calls) == 1
    assert ".rss" in calls[0]


# --------------------------------------------------------------------- #
# v0.3 Twitter / X handler via Nitter rotation
# --------------------------------------------------------------------- #


def _make_state_with_nitter(*instances: str) -> AppState:
    from tests.conftest import make_default_state

    s = AppSettings(nitter_instances=list(instances))
    return make_default_state(settings=s)


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

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        assert "nitter.example.com" in url
        return FakeCurlResp(200, text=tweet_html)

    patch_curl_session(monkeypatch, handler)

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

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        seen.append(url)
        # First instance always fails (5xx), second succeeds.
        if "fail.example.com" in url:
            return FakeCurlResp(503)
        return FakeCurlResp(200, text=tweet_html)

    patch_curl_session(monkeypatch, handler)

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

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(503)

    patch_curl_session(monkeypatch, handler)

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


# NOTE: permalink-focus, crosspost annotation, and `[removed]`-body marking
# were `.json`-only capabilities. The keyless `.rss` projection is FLAT and
# carries none of that structure, so those renders (and their tests) were
# retired in the RSS switch. A comment permalink now routes to the whole
# thread `.rss`, rendered flat (`_detect_permalink` still classifies the
# shape so the caller knows a specific comment was requested).


@pytest.mark.asyncio
async def test_reddit_handler_signals_archive_on_404_when_old_reddit_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When .json 404 AND old.reddit 404, return not_found with archive hint.

    The playbook reads `verdict=not_found` on a reddit URL and dispatches
    the archive tier next.
    """

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(404)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/comments/dead/title/", state=_make_state())

    assert result.verdict == Verdict.not_found
    assert result.pre_rendered is None
    assert result.operator_hint is not None
    assert result.operator_hint.code == "reddit_deleted_try_archive"


@pytest.mark.asyncio
async def test_reddit_handler_signals_archive_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Thread 403 (quarantined/NSFW/private) skips old.reddit and asks for archive."""

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(403)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/comments/abc/title/", state=_make_state())

    assert result.verdict == Verdict.not_found
    assert result.operator_hint is not None
    assert result.operator_hint.code == "reddit_forbidden_try_archive"


@pytest.mark.asyncio
async def test_reddit_search_403_fails_loud_with_eager_browser_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hard block on a search/listing surface is terminal → fail loud.

    Never-silently-miss tenet: the handler emits `block_page_detected`
    (so the envelope's `retrieval_incomplete` flag is set) plus the critical
    `try_user_browser` operator hint, EAGERLY — the archive/browser ladder
    can't recover a dynamic search surface.
    """

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(403)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/x/search/?q=bell", state=_make_state())

    assert result.verdict == Verdict.block_page_detected
    assert result.pre_rendered is None
    assert result.operator_hint is not None
    assert result.operator_hint.code == "try_user_browser"
    assert result.operator_hint.severity == "critical"


@pytest.mark.asyncio
async def test_reddit_rss_429_fails_loud_after_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated RSS 429s exhaust the bounded backoff, then fail loud (never silent)."""
    monkeypatch.setattr("a2web.handlers.reddit._RSS_BACKOFF_S", ())  # no sleeping in tests
    calls: list[str] = []

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        calls.append(url)
        return FakeCurlResp(429)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/", state=_make_state())

    assert result.verdict == Verdict.rate_limited
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_reddit_handler_resolves_short_url_then_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redd.it/<id> → HEAD-resolved (via 301) → recursed → renders the thread via .rss."""
    resolved_url = "https://www.reddit.com/r/gravelcycling/comments/1qcwxml/new_bike_day/"

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if "redd.it" in url:
            # Simulate curl_cffi having followed the 301 redirect — the
            # final_url is the resolved reddit URL the handler reads.
            return FakeCurlResp(200, url=resolved_url, body=b"")
        if ".rss" in url:
            return FakeCurlResp(200, body=_rss_bytes("thread.rss"), content_type="application/atom+xml")
        return FakeCurlResp(404)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://redd.it/abc", state=_make_state())

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.title == "New bike day"


@pytest.mark.asyncio
async def test_reddit_handler_short_url_no_match_for_non_thread_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If redd.it resolves to a non-thread URL, return no_match=True."""
    resolved_url = "https://www.reddit.com/r/x/"

    def handler(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if "redd.it" in url:
            # Simulate curl_cffi having followed the 301 redirect.
            return FakeCurlResp(200, url=resolved_url)
        return FakeCurlResp(200)

    patch_curl_session(monkeypatch, handler)

    result = await RedditHandler().fetch("https://redd.it/abc", state=_make_state())

    assert result.no_match is True
    assert result.final_url == resolved_url


def test_playbook_escalates_reddit_not_found_to_archive() -> None:
    """decide_next: reddit comment URL + handler not_found → RetryViaArchive."""
    from a2web.actions import PlannerCaps, RetryViaArchive, decide_next
    from a2web.decision_log import Observation, ObservationKind

    url = "https://www.reddit.com/r/x/comments/dead/"
    log = [Observation(ObservationKind.tier_outcome, "site_handler:reddit", Verdict.not_found, True, 1)]
    action = decide_next(log, url=url, caps=PlannerCaps(0, 0, 0, 0))
    assert isinstance(action, RetryViaArchive)
    assert action.url == url


def test_playbook_does_not_escalate_not_found_on_other_hosts() -> None:
    """The reddit not_found rule does not fire for non-reddit hosts."""
    from a2web.actions import Continue, PlannerCaps, decide_next
    from a2web.decision_log import Observation, ObservationKind

    log = [Observation(ObservationKind.tier_outcome, "raw", Verdict.not_found, False, 1)]
    action = decide_next(log, url="https://example.com/page", caps=PlannerCaps(0, 0, 0, 0))
    assert isinstance(action, Continue)
