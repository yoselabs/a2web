"""Arxiv handler tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from a2web.handlers import ArxivHandler, match_handler
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState

_FIX = Path(__file__).parent / "fixtures"


def _state() -> AppState:
    return AppState(settings=AppSettings())


def test_match_handler_returns_arxiv() -> None:
    h = match_handler("https://arxiv.org/abs/2401.12345")
    assert isinstance(h, ArxivHandler)


def test_arxiv_matches_versioned_id() -> None:
    assert ArxivHandler().matches("https://arxiv.org/abs/2401.12345v3")


def test_arxiv_does_not_match_pdf_path() -> None:
    # pdf URLs are rewritten to abs by the playbook (PR7b) before reaching handler
    assert not ArxivHandler().matches("https://arxiv.org/pdf/2401.12345")


def test_arxiv_does_not_match_listing() -> None:
    assert not ArxivHandler().matches("https://arxiv.org/list/cs.DC/2401")


@pytest.mark.asyncio
async def test_arxiv_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    atom = (_FIX / "arxiv_query.atom.xml").read_text()

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, text=atom, headers={"content-type": "application/atom+xml"})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.tier_extras["pre_rendered"]
    assert pre["title"].startswith("A Study of Concurrent Coffee")
    assert "Alice Example" in pre["byline"]
    assert "Bob Example" in pre["byline"]
    assert "cs.DC" in pre["content_md"]
    assert "Categories" in pre["content_md"]


@pytest.mark.asyncio
async def test_arxiv_unknown_id_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_atom = '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, text=empty_atom)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/9999.99999", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_arxiv_malformed_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, text="not xml at all <<<")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.content_type_mismatch


@pytest.mark.asyncio
async def test_arxiv_429_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(429, text="")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.rate_limited
