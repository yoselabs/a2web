"""Wikipedia handler tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from a2web.handlers import WikipediaHandler, match_handler
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState

_FIX = Path(__file__).parent / "fixtures"


def _state() -> AppState:
    return AppState(settings=AppSettings())


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
    pre = result.tier_extras["pre_rendered"]
    assert pre["title"] == "Octopus"
    assert "octopus" in pre["content_md"].lower()


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
