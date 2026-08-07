"""A hint must never name a field the envelope it ships on does not carry (a2web-7bj.3).

Originally fixed by retargeting `content_thin`/`content_empty` hints between two
field names (`content_md` on `FetchResponse`, `thin_content` on `AskResponse`).
a2web-brn then removed `thin_content` entirely — the body is always `content_md`
now, forced onto the wire on `AskResponse` when the withheld-body index (ADR-0015)
requires it, so the retargeting problem this test originally guarded no longer has
two field names to retarget between. What's left worth guarding: the hint text
names `content_md` on every envelope shape and every `include_content` setting.

Uses the same live-pipeline harness as `test_thin_semantics.py` — a hint built off
a synthetic `FetchContext` would not prove the wiring actually runs end to end.
"""

from __future__ import annotations

import re

import pytest

from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.models import Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests.conftest import make_default_state

_EMPTY_RESULTS_HTML = (
    b"<html><body><main><h1>Search results</h1>"
    b"<p>Aradiginiz urun bulunamadi. No products matched your search for "
    b"&quot;zzzqqxnonexistent&quot;. Try different keywords, check your spelling, "
    b"or browse our popular categories for related items.</p>"
    b"</main></body></html>"
)


def _html_tier(name: str, *, body: bytes, verdict: Verdict = Verdict.ok, status_code: int = 200) -> object:
    class _T:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=body, content_type="text/html", status_code=status_code, final_url=url, verdict=verdict)

    _T.name = name  # type: ignore[attr-defined]
    return _T()


def _names_content_md(text: str) -> bool:
    return re.search(r"`content_md`", text) is not None


@pytest.mark.asyncio
async def test_fetch_raw_envelope_hint_names_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fetch_raw` returns a bare `FetchResponse` — the body is always in `content_md`."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), debug=True)

    hint = next(h for h in fr.operator_hints if h.code == "content_thin")
    assert _names_content_md(hint.message)
    assert _names_content_md(hint.fix)


@pytest.mark.asyncio
@pytest.mark.protects("spec:ask-response", "Requirement: content_thin and content_empty hints name content_md")
async def test_ask_envelope_withholding_content_still_names_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ask`'s default `include_content=False` — the body is forced onto `content_md` anyway."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), ask="what did I find?", debug=True)
    ar = build_ask_response(fr, include_content=False, debug=False)

    assert ar.content_md
    hint = next(h for h in ar.operator_hints if h.code == "content_thin")
    assert _names_content_md(hint.message)
    assert _names_content_md(hint.fix)


@pytest.mark.asyncio
@pytest.mark.protects("spec:ask-response", "Requirement: content_thin and content_empty hints name content_md")
async def test_ask_envelope_with_include_content_names_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """`include_content=True` — same field, same hint text."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), ask="what did I find?", debug=True)
    ar = build_ask_response(fr, include_content=True, debug=False)

    assert ar.content_md
    hint = next(h for h in ar.operator_hints if h.code == "content_thin")
    assert _names_content_md(hint.message)
    assert _names_content_md(hint.fix)
