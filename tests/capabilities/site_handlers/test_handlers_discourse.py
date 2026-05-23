"""Discourse handler tests — topic threading, index next_links, host allowlist."""

from __future__ import annotations

from typing import Any

import pytest

from a2web.handlers import DiscourseHandler, match_handler
from a2web.handlers.discourse import _render_index, _render_topic
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def _state() -> AppState:
    return make_default_state()


def _settings() -> AppSettings:
    return make_default_state().settings


# --------------------------------------------------------------------- #
# matches() — the configured-host allowlist
# --------------------------------------------------------------------- #


def test_match_handler_returns_discourse_for_configured_topic_url() -> None:
    h = match_handler("https://linux.do/t/some-topic/123", _settings())
    assert isinstance(h, DiscourseHandler)


def test_discourse_matches_configured_host() -> None:
    s = _settings()
    assert DiscourseHandler().matches("https://linux.do/t/x/1", s)
    assert DiscourseHandler().matches("https://meta.discourse.org/latest", s)


def test_discourse_does_not_match_non_allowlisted_host() -> None:
    assert not DiscourseHandler().matches("https://example.com/t/x/1", _settings())
    assert match_handler("https://example.com/t/x/1", _settings()) is None


def test_discourse_matches_falls_back_to_defaults_without_settings() -> None:
    """No settings passed → the default allowlist still claims linux.do."""
    assert DiscourseHandler().matches("https://linux.do/t/x/1")


# --------------------------------------------------------------------- #
# Topic rendering
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_topic_url_renders_threaded_post_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    topic = (_FIX / "discourse_topic.json").read_text()

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=topic, headers={"content-type": "application/json"})

    patch_curl_session(monkeypatch, _fake_get)

    result = await DiscourseHandler().fetch("https://linux.do/t/how-do-i-configure/123", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre is not None
    assert pre.title == "How do I configure the thing?"
    assert pre.byline == "alice"
    assert "## Discussion" in pre.content_md
    # post 2 replies to the OP (depth 1); post 3 replies to post 2 (depth 2)
    assert "> You need to set" in pre.content_md
    assert ">> That worked, thanks Bob!" in pre.content_md
    # the cooked-HTML link is preserved as markdown
    assert "[the docs](https://meta.discourse.org/docs)" in pre.content_md


@pytest.mark.asyncio
async def test_topic_url_without_post_stream_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text='{"title": "not a discourse topic"}')

    patch_curl_session(monkeypatch, _fake_get)

    result = await DiscourseHandler().fetch("https://linux.do/t/x/1", state=_state())
    assert result.verdict == Verdict.not_found


# --------------------------------------------------------------------- #
# Forum-index rendering
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_index_url_emits_discussion_next_links(monkeypatch: pytest.MonkeyPatch) -> None:
    latest = (_FIX / "discourse_latest.json").read_text()

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=latest, headers={"content-type": "application/json"})

    patch_curl_session(monkeypatch, _fake_get)

    result = await DiscourseHandler().fetch("https://linux.do/latest", state=_state())
    assert result.verdict == Verdict.ok
    assert len(result.next_links) == 3
    assert all(nl.kind == "discussion" for nl in result.next_links)
    assert result.next_links[0].url == "https://linux.do/t/first-topic-about-configuration/101"


@pytest.mark.asyncio
async def test_configured_host_non_discourse_json_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text='{"foo": "bar"}')

    patch_curl_session(monkeypatch, _fake_get)

    result = await DiscourseHandler().fetch("https://linux.do/", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_non_200_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(503, text="")

    patch_curl_session(monkeypatch, _fake_get)

    result = await DiscourseHandler().fetch("https://linux.do/t/x/1", state=_state())
    assert result.verdict == Verdict.connection_error


# --------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------- #


def test_render_topic_rejects_non_discourse_payload() -> None:
    assert _render_topic({"title": "x"}) is None
    assert _render_topic([]) is None


def test_render_index_rejects_non_discourse_payload() -> None:
    assert _render_index({"foo": "bar"}, "https://linux.do/latest") is None


def test_render_topic_decodes_html_entities_in_fancy_title() -> None:
    """Regression: Discourse `fancy_title` carries HTML entities (`&rsquo;`,
    `&amp;`); the rendered title MUST be human-readable, not raw entities."""
    payload = {
        "id": 1,
        "fancy_title": "It&rsquo;s a &ldquo;test&rdquo; &amp; should decode",
        "post_stream": {"posts": [{"id": 1, "post_number": 1, "username": "alice", "cooked": "<p>body</p>"}]},
    }
    rendered = _render_topic(payload)
    assert rendered is not None
    assert "&rsquo;" not in rendered["title"]
    assert "&amp;" not in rendered["title"]
    assert "’" in rendered["title"]  # noqa: RUF001
    assert "&" in rendered["title"]  # the decoded ampersand
    # Sanity — the title also appears in the rendered content_md
    assert "&rsquo;" not in rendered["content_md"]


def test_render_index_decodes_html_entities_in_fancy_title() -> None:
    """The latest-topics index renders `fancy_title` for each entry — same rule."""
    payload = {
        "topic_list": {
            "topics": [
                {
                    "id": 99,
                    "fancy_title": "Tom&rsquo;s thread",
                    "slug": "toms-thread",
                    "posts_count": 3,
                    "reply_count": 2,
                },
            ],
        },
    }
    rendered = _render_index(payload, "https://linux.do/latest")
    assert rendered is not None
    assert "&rsquo;" not in rendered["content_md"]
    assert "Tom’s" in rendered["content_md"]  # noqa: RUF001
