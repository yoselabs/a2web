"""Arxiv handler tests."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from dom_schema import Yield

from a2web.handlers import ArxivHandler, match_handler
from a2web.handlers.arxiv import _parse_listing
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


#: The captured page's own entry count, established once by inspection. NOT the
#: count arXiv advertises for itself — there is no single such number (per-section
#: `showing N of M`, a `showing first N of M` partial marker, `Total of 408
#: entries`) and the page renders a variable number of day-sections.
_CAPTURED_ARXIV_ENTRIES = 47


def _captured(name: str) -> str:
    path = pathlib.Path(__file__).parents[2] / "fixtures" / "captured" / name
    assert path.exists(), f"captured fixture missing: {path}. Re-capture it; never hand-write one."
    return path.read_text(encoding="utf-8")


def test_arxiv_listing_parses_a_captured_live_page() -> None:
    """The ORACLE for "does this parser match arXiv" — captured, never hand-written.

    The test this replaces was GREEN while the handler returned ZERO entries on
    the live site, because its fixture used `<a href="/abs/…">arXiv:…</a>` with
    double quotes and flush anchor text — the shape the regex expected, authored
    from the same mental model as the regex. arXiv serves single-quoted
    attributes and `<a href ="…">`. A fixture written from the parser's own
    assumptions cannot fail when those assumptions are wrong about the site; it
    can only confirm the parser agrees with itself.

    A failure here after a re-capture means arXiv changed and the schema must
    follow. It is NOT a reason to weaken the assertion.
    """
    parsed = _parse_listing(_captured("arxiv_list_cs_CL_recent.html"))

    assert parsed.verdict is Yield.OK, f"verdict={parsed.verdict} on a captured arXiv listing"
    assert len(parsed.rows) == _CAPTURED_ARXIV_ENTRIES
    first = parsed.rows[0]
    assert first["id"] == "2607.22529"
    assert first["title"].startswith("Skill Self-Play")
    assert "Siyuan Huang" in first["authors"]


def test_arxiv_listing_reports_rot_not_an_empty_listing() -> None:
    """A page that is not an arXiv listing must blame the SCHEMA, never the page.

    This is the guard that would have caught the real defect: the old parser
    returned `[]` and the handler rendered `## Papers (0)` with `Verdict.ok`,
    which is indistinguishable from a quiet day.
    """
    parsed = _parse_listing("<html><body><section class='articles'><dt>x</dt></section></body></html>")

    assert parsed.verdict is Yield.ROT
    assert parsed.is_rot


def test_arxiv_listing_empty_container_is_empty_not_rot() -> None:
    """A real arXiv listing with no entries is a fact about the PAGE."""
    parsed = _parse_listing("<html><body><dl id='articles'></dl></body></html>")

    assert parsed.verdict is Yield.EMPTY
    assert not parsed.is_rot


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
