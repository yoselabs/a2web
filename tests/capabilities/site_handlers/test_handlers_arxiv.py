"""Arxiv handler tests."""

from __future__ import annotations

from typing import Any

import pytest

from a2web.handlers import ArxivHandler, match_handler
from a2web.models import Verdict
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def _state() -> AppState:
    return make_default_state()


def test_match_handler_returns_arxiv() -> None:
    h = match_handler("https://arxiv.org/abs/2401.12345")
    assert isinstance(h, ArxivHandler)


def test_arxiv_matches_versioned_id() -> None:
    assert ArxivHandler().matches("https://arxiv.org/abs/2401.12345v3")


def test_arxiv_does_not_match_pdf_path() -> None:
    # pdf URLs are rewritten to abs by the playbook (PR7b) before reaching handler
    assert not ArxivHandler().matches("https://arxiv.org/pdf/2401.12345")


def test_arxiv_matches_listing() -> None:
    """v0.7 link-discovery: arxiv handler matches `/list/<cat>/<window>` for candidate population."""
    assert ArxivHandler().matches("https://arxiv.org/list/cs.DC/2401")
    assert ArxivHandler().matches("https://arxiv.org/list/cs.LG/recent")


def test_arxiv_listing_candidates_shape() -> None:
    """`_listing_candidates` yields up to 10 NextLink entries with drilldown kind."""
    from a2web.handlers.arxiv import _listing_candidates

    entries = [{"id": f"2401.{1000 + i}", "title": f"Paper {i}", "authors": "Alice, Bob"} for i in range(15)]
    cands = _listing_candidates(entries)
    assert len(cands) == 10
    assert cands[0].kind == "drilldown"
    assert cands[0].url == "https://arxiv.org/abs/2401.1000"
    assert cands[0].anchor == "Paper 0"
    assert cands[0].reason == "Alice, Bob"


def test_arxiv_listing_html_parser_extracts_entries() -> None:
    """`_parse_listing_entries` pulls (id, title, authors) per `<dt><dd>` block."""
    from a2web.handlers.arxiv import _parse_listing_entries

    html = """
    <dl>
      <dt><a href="/abs/2401.0001">arXiv:2401.0001</a></dt>
      <dd>
        <div class="list-title mathjax"><span class="descriptor">Title:</span> First paper</div>
        <div class="list-authors"><span class="descriptor">Authors:</span> <a href="x">Alice</a>, <a href="y">Bob</a></div>
      </dd>
      <dt><a href="/abs/2401.0002">arXiv:2401.0002</a></dt>
      <dd>
        <div class="list-title mathjax"><span class="descriptor">Title:</span> Second paper</div>
        <div class="list-authors"><span class="descriptor">Authors:</span> Carol</div>
      </dd>
    </dl>
    """
    entries = _parse_listing_entries(html)
    assert len(entries) == 2
    assert entries[0] == {"id": "2401.0001", "title": "First paper", "authors": "Alice, Bob"}
    assert entries[1]["id"] == "2401.0002"
    assert entries[1]["authors"] == "Carol"


@pytest.mark.asyncio
async def test_arxiv_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    atom = (_FIX / "arxiv_query.atom.xml").read_text()

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=atom, headers={"content-type": "application/atom+xml"})

    patch_curl_session(monkeypatch, _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre.title.startswith("A Study of Concurrent Coffee")
    assert "Alice Example" in pre.byline
    assert "Bob Example" in pre.byline
    assert "cs.DC" in pre.content_md
    assert "Categories" in pre.content_md


@pytest.mark.asyncio
async def test_arxiv_unknown_id_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_atom = '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=empty_atom)

    patch_curl_session(monkeypatch, _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/9999.99999", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_arxiv_malformed_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text="not xml at all <<<")

    patch_curl_session(monkeypatch, _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.content_type_mismatch


@pytest.mark.asyncio
async def test_arxiv_429_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(429, text="")

    patch_curl_session(monkeypatch, _fake_get)

    result = await ArxivHandler().fetch("https://arxiv.org/abs/2401.12345", state=_state())
    assert result.verdict == Verdict.rate_limited
