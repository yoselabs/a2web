"""A hint must never name a field the envelope it ships on does not carry (a2web-7bj.3).

`content_thin_hint`/`content_empty_hint` are created at the terminal-classification
phase — before it is known whether this fetch will surface as a `FetchResponse`
(body always in `content_md`) or project into an `AskResponse` (body in
`thin_content` whenever `content_md` would otherwise be withheld, `content_md`
directly otherwise). The DHL-session audit caught the hint unconditionally naming
`thin_content` — a field `FetchResponse` never has, and one `AskResponse` doesn't
populate when `include_content=True`. `build_ask_response` now retargets the hint
to the field that is actually populated on the envelope it is about to ship on.

Uses the same live-pipeline harness as `test_thin_semantics.py` — a hint built off
a synthetic `FetchContext` would not prove the retargeting actually runs.
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


def _referenced_field(text: str) -> str | None:
    m = re.search(r"`(content_md|thin_content)`", text)
    return m.group(1) if m else None


@pytest.mark.asyncio
async def test_fetch_raw_envelope_hint_names_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fetch_raw` returns a bare `FetchResponse` — the body is always in `content_md`."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), debug=True)

    hint = next(h for h in fr.operator_hints if h.code == "content_thin")
    assert _referenced_field(hint.message) == "content_md"
    assert _referenced_field(hint.fix) == "content_md"


@pytest.mark.asyncio
@pytest.mark.protects(
    "spec:ask-response", "Requirement: content_thin and content_empty hints name a field the shipping envelope actually carries"
)
async def test_ask_envelope_withholding_content_names_thin_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ask`'s default `include_content=False` — the body actually rides `thin_content`."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), ask="what did I find?", debug=True)
    ar = build_ask_response(fr, include_content=False, debug=False)

    assert ar.thin_content is not None
    hint = next(h for h in ar.operator_hints if h.code == "content_thin")
    assert _referenced_field(hint.message) == "thin_content"
    assert _referenced_field(hint.fix) == "thin_content"


@pytest.mark.asyncio
@pytest.mark.protects(
    "spec:ask-response", "Requirement: content_thin and content_empty hints name a field the shipping envelope actually carries"
)
async def test_ask_envelope_with_include_content_names_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """`include_content=True` — `content_md` carries the body directly; `thin_content`
    is never populated (would duplicate it, a2web-y5m), so the hint must still point
    at `content_md`, not the field that stayed empty."""
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), ask="what did I find?", debug=True)
    ar = build_ask_response(fr, include_content=True, debug=False)

    assert ar.content_md
    assert ar.thin_content is None
    hint = next(h for h in ar.operator_hints if h.code == "content_thin")
    assert _referenced_field(hint.message) == "content_md"
    assert _referenced_field(hint.fix) == "content_md"
