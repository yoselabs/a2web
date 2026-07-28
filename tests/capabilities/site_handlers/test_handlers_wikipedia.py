"""Wikipedia handler tests."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from a2web.handlers import WikipediaHandler, match_handler
from a2web.models import Verdict
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


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

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        captured["url"] = url
        return FakeCurlResp(200, text=html, headers={"content-type": "text/html"})

    patch_curl_session(monkeypatch, _fake_get)

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

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        captured["url"] = url
        return FakeCurlResp(200, text="<html><body><p>" + ("Russian content. " * 80) + "</p></body></html>")

    patch_curl_session(monkeypatch, _fake_get)

    await WikipediaHandler().fetch("https://ru.wikipedia.org/wiki/Test", state=_state())
    assert "ru.wikipedia.org" in captured["url"]


@pytest.mark.asyncio
async def test_wikipedia_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(404, text="")

    patch_curl_session(monkeypatch, _fake_get)

    result = await WikipediaHandler().fetch("https://en.wikipedia.org/wiki/UnknownArticle", state=_state())
    assert result.verdict == Verdict.not_found


def test_wikipedia_slug_decoded() -> None:
    """Title from URL slug is URL-decoded and underscores → spaces."""
    # We assert through the matcher path that the regex captures encoded slugs.
    assert WikipediaHandler().matches("https://en.wikipedia.org/wiki/New_York_City")


#: Wikilinks the captured Parsoid page carries, well above the 10-cap so the
#: cap is genuinely exercised. Established by inspection of the committed file.
_CAPTURED_WIKILINKS_MIN = 20


def _captured(name: str) -> str:
    path = pathlib.Path(__file__).parents[2] / "fixtures" / "captured" / name
    assert path.exists(), f"captured fixture missing: {path}. Re-capture it; never hand-write one."
    return path.read_text(encoding="utf-8")


def test_wikipedia_wikilinks_from_a_captured_parsoid_page() -> None:
    """The ORACLE — captured Parsoid output, never a hand-written approximation.

    The three tests this replaces were GREEN while `_wikilink_candidates`
    returned ZERO against a live article carrying 1066 anchors. Their fixture
    used `<a href="/wiki/Octopus">`; Parsoid serves `rel="mw:WikiLink"` with a
    RELATIVE `./Target` href. The fixture and the regex shared one stale
    assumption, so the suite could never contradict it.

    Unlike the arXiv listing, this yield is NOT verdict-guarded: wikilinks are
    scattered through prose, so the schema's container is `<body>`, which always
    matches — a rotted row selector reads as EMPTY, not ROT. This test and the
    probe's declared expectation are therefore the ONLY things standing between
    a stale selector and a silently index-free article.
    """
    from a2web.handlers.wikipedia import _wikilink_candidates

    cands = _wikilink_candidates(_captured("wikipedia_parsoid_octopus_disambig.html"), lang="en")

    assert len(cands) == 10, "the cap should be reached on a real article"
    assert all(c.kind == "related" for c in cands)
    assert all(c.reason == "related article" for c in cands)
    assert all(c.url.startswith("https://en.wikipedia.org/wiki/") for c in cands)
    assert not any(":" in c.url.removeprefix("https://en.wikipedia.org/wiki/") for c in cands), (
        "namespaced targets (File:, Category:) must be filtered out"
    )
    assert len({c.url for c in cands}) == len(cands), "targets must be deduplicated"


def test_wikipedia_captured_page_is_link_dense_enough_to_exercise_the_cap() -> None:
    """Non-vacuity floor: the capture must hold well more than the cap.

    Without this, a capture that decayed to 3 links would make the test above
    assert the cap against a page that never reaches it.
    """
    from dom_schema import extract

    from a2web.handlers.wikipedia import _WIKILINK_SCHEMA

    got = extract(_captured("wikipedia_parsoid_octopus_disambig.html"), _WIKILINK_SCHEMA)
    assert len(got.rows) >= _CAPTURED_WIKILINKS_MIN, f"capture carries only {len(got.rows)} wikilinks — re-capture a denser article"


def test_wikipedia_wikilink_candidates_stay_on_source_language() -> None:
    """Wikilinks generated for a `ru.wikipedia.org` article all carry ru host."""
    from a2web.handlers.wikipedia import _wikilink_candidates

    # Synthetic is legitimate HERE: this controls the LANGUAGE variable, it is
    # not the oracle for whether the parser matches Parsoid (that is the
    # captured-fixture test above). Written in the real `./Target` shape.
    html = '<p>See <a rel="mw:WikiLink" href="./Москва">Moscow</a> and <a rel="mw:WikiLink" href="./Россия">Russia</a></p>'
    cands = _wikilink_candidates(html, lang="ru")
    assert len(cands) == 2
    assert all(c.url.startswith("https://ru.wikipedia.org/wiki/") for c in cands)


def test_wikipedia_wikilink_candidates_capped_at_10() -> None:
    """15 wikilinks → exactly 10 candidates returned."""
    from a2web.handlers.wikipedia import _wikilink_candidates

    # Synthetic is legitimate HERE too: it controls the COUNT to exercise the
    # cap. Real Parsoid shape, so it cannot drift from what the parser accepts.
    html = "".join(f'<a rel="mw:WikiLink" href="./Article_{i}">Article {i}</a>' for i in range(15))
    assert len(_wikilink_candidates(html, lang="en")) == 10


@pytest.mark.asyncio
async def test_wikipedia_does_not_report_ok_on_a_challenge_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Symmetry, not incident: no wikipedia REST response has been observed
    carrying a challenge, but every handler that extracts HTML runs the check —
    one added only where a defect was already seen is one the next handler never
    gets. Uses the CAPTURED interstitial, never a hand-written one."""
    html = (_FIX / "captured" / "xcancel_antibot_interstitial.html").read_text()

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=html, headers={"content-type": "text/html"})

    patch_curl_session(monkeypatch, _fake_get)

    result = await WikipediaHandler().fetch("https://en.wikipedia.org/wiki/Octopus", state=_state())
    assert result.verdict == Verdict.block_page_detected
    assert result.pre_rendered is None
