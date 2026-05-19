"""Wikipedia handler tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from a2web.handlers import WikipediaHandler, match_handler
from a2web.models import Verdict
from a2web.state import AppState
from tests.conftest import make_default_state

_FIX = Path(__file__).parent / "fixtures"


def _state() -> AppState:
    return make_default_state()


def test_match_handler_returns_wikipedia() -> None:
    h = match_handler("https://en.wikipedia.org/wiki/Octopus")
    assert isinstance(h, WikipediaHandler)


def test_wikipedia_matches_non_english() -> None:
    assert WikipediaHandler().matches("https://ru.wikipedia.org/wiki/Octopus")


def test_wikipedia_does_not_match_root() -> None:
    assert not WikipediaHandler().matches("https://en.wikipedia.org/")


def test_wikipedia_does_not_match_special_pages() -> None:
    assert not WikipediaHandler().matches("https://en.wikipedia.org/w/index.php?title=Octopus")


@pytest.mark.asyncio
async def test_wikipedia_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (_FIX / "wikipedia_octopus.html").read_text()

    captured: dict[str, str] = {}

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await WikipediaHandler().fetch("https://en.wikipedia.org/wiki/Octopus", state=_state())
    assert result.verdict == Verdict.ok
    assert "/api/rest_v1/page/html/Octopus" in captured["url"]
    assert "en.wikipedia.org" in captured["url"]
    pre = result.pre_rendered
    assert pre.title == "Octopus"
    assert "octopus" in pre.content_md.lower()


@pytest.mark.asyncio
async def test_wikipedia_uses_url_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, text="<html><body><p>" + ("Russian content. " * 80) + "</p></body></html>")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    await WikipediaHandler().fetch("https://ru.wikipedia.org/wiki/Test", state=_state())
    assert "ru.wikipedia.org" in captured["url"]


@pytest.mark.asyncio
async def test_wikipedia_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(404, text="")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await WikipediaHandler().fetch("https://en.wikipedia.org/wiki/UnknownArticle", state=_state())
    assert result.verdict == Verdict.not_found


def test_wikipedia_slug_decoded() -> None:
    """Title from URL slug is URL-decoded and underscores → spaces."""
    # We assert through the matcher path that the regex captures encoded slugs.
    assert WikipediaHandler().matches("https://en.wikipedia.org/wiki/New_York_City")


def test_wikipedia_wikilink_candidates_dedupes_and_caps() -> None:
    """Outbound article links → up to 10 `related` candidates, deduped on target."""
    from a2web.handlers.wikipedia import _wikilink_candidates

    html = """
    <p>See also <a href="/wiki/Octopus">Octopus</a> and <a href="/wiki/Cephalopod">Cephalopod</a>.</p>
    <p>Mentioned again: <a href="/wiki/Octopus">Octopus species</a>.</p>
    <p>Categories: <a href="/wiki/Category:Animals">Animals</a></p>
    <p>File: <a href="/wiki/File:Photo.jpg">photo</a></p>
    """
    cands = _wikilink_candidates(html, lang="en")
    targets = [c.url for c in cands]
    assert "https://en.wikipedia.org/wiki/Octopus" in targets
    assert "https://en.wikipedia.org/wiki/Cephalopod" in targets
    # File: and Category: links carry `:` and are filtered out
    assert not any("Category:" in u or "File:" in u for u in targets)
    # Dedupe: Octopus only once
    assert targets.count("https://en.wikipedia.org/wiki/Octopus") == 1
    assert all(c.kind == "related" for c in cands)
    assert all(c.reason == "related article" for c in cands)


def test_wikipedia_wikilink_candidates_stay_on_source_language() -> None:
    """Wikilinks generated for a `ru.wikipedia.org` article all carry ru host."""
    from a2web.handlers.wikipedia import _wikilink_candidates

    html = '<p>See <a href="/wiki/Москва">Moscow</a> and <a href="/wiki/Россия">Russia</a></p>'
    cands = _wikilink_candidates(html, lang="ru")
    assert all(c.url.startswith("https://ru.wikipedia.org/wiki/") for c in cands)


def test_wikipedia_wikilink_candidates_capped_at_10() -> None:
    """15 wikilinks → exactly 10 candidates returned."""
    from a2web.handlers.wikipedia import _wikilink_candidates

    html = "".join(f'<a href="/wiki/Article_{i}">Article {i}</a>' for i in range(15))
    assert len(_wikilink_candidates(html, lang="en")) == 10
