"""Habr handler tests — kek/v2 article + threaded comments, URL forms, locale."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from a2web.handlers import HabrHandler, match_handler
from a2web.handlers.habr import _html_to_md, _parse
from a2web.models import Verdict
from a2web.state import AppState
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def _state() -> AppState:
    return make_default_state()


def _responder(
    *, article_status: int = 200, comments_status: int = 200, captured: dict[str, Any] | None = None
):
    """Build a fake `httpx.AsyncClient.get` routing on the endpoint path."""
    article = (_FIX / "habr_article.json").read_text()
    comments = (_FIX / "habr_comments.json").read_text()

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if captured is not None:
            captured[url] = kwargs.get("params") or {}
        if url.endswith("/comments/"):
            return httpx.Response(comments_status, text=comments if comments_status == 200 else "")
        return httpx.Response(article_status, text=article if article_status == 200 else "")

    return _fake_get


# --------------------------------------------------------------------- #
# URL parsing / matching
# --------------------------------------------------------------------- #


def test_match_handler_returns_habr() -> None:
    assert isinstance(match_handler("https://habr.com/ru/articles/1032730/"), HabrHandler)


def test_habr_matches_all_url_forms() -> None:
    h = HabrHandler()
    assert h.matches("https://habr.com/ru/articles/123/")
    assert h.matches("https://habr.com/en/articles/123/")
    assert h.matches("https://habr.com/ru/companies/acme/articles/123/")
    assert h.matches("https://habr.com/ru/post/123/")
    assert h.matches("https://habr.com/ru/company/acme/blog/123/")
    assert h.matches("https://habr.com/articles/123")


def test_habr_does_not_match_non_article_urls() -> None:
    assert not HabrHandler().matches("https://habr.com/ru/articles/")
    assert not HabrHandler().matches("https://example.com/ru/articles/123/")
    assert match_handler("https://example.com/ru/articles/123/") is None


def test_parse_extracts_id_and_language() -> None:
    assert _parse("https://habr.com/en/articles/555/") == ("555", "en")
    assert _parse("https://habr.com/ru/articles/555/") == ("555", "ru")
    # language segment absent → defaults to ru
    assert _parse("https://habr.com/articles/555/") == ("555", "ru")
    assert _parse("https://habr.com/ru/companies/acme/articles/777/") == ("777", "ru")
    assert _parse("https://example.com/ru/articles/1/") is None


# --------------------------------------------------------------------- #
# fetch()
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_article_renders_body_and_threaded_discussion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "get", _responder())

    result = await HabrHandler().fetch("https://habr.com/ru/articles/1032730/", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre is not None
    assert pre.title == "How to fix the IT overload crisis"
    assert pre.byline == "Andrey_Biryukov"
    assert "managing the IT overload crisis" in pre.content_md
    assert "[the reference](https://example.com/ref)" in pre.content_md
    assert "## Discussion" in pre.content_md
    # root comment at depth 1, its reply nested at depth 2
    assert "> Great article" in pre.content_md
    assert ">> I disagree" in pre.content_md
    assert "> A separate top-level point" in pre.content_md


@pytest.mark.asyncio
async def test_comments_failure_degrades_to_article_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "get", _responder(comments_status=500))

    result = await HabrHandler().fetch("https://habr.com/ru/articles/1032730/", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre is not None
    assert "managing the IT overload crisis" in pre.content_md
    assert "## Discussion" not in pre.content_md


@pytest.mark.asyncio
async def test_unknown_id_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "get", _responder(article_status=404))

    result = await HabrHandler().fetch("https://habr.com/ru/articles/9999999/", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_language_segment_selects_api_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(httpx.AsyncClient, "get", _responder(captured=captured))

    await HabrHandler().fetch("https://habr.com/en/articles/1032730/", state=_state())
    assert all(p == {"fl": "en", "hl": "en"} for p in captured.values())

    captured.clear()
    await HabrHandler().fetch("https://habr.com/ru/articles/1032730/", state=_state())
    assert all(p == {"fl": "ru", "hl": "ru"} for p in captured.values())


# --------------------------------------------------------------------- #
# Render helper
# --------------------------------------------------------------------- #


def test_html_to_md_preserves_links_and_strips_tags() -> None:
    md = _html_to_md('<div><p>Hello <strong>world</strong> <a href="https://e.com">link</a>.</p></div>')
    assert "**world**" in md
    assert "[link](https://e.com)" in md
    assert "<p>" not in md
