"""End-to-end: corroborated empty → ok promotion (empty-vs-wall-discrimination).

A retrieved thin 200 that reads as an empty result set is promoted to `status: ok`
with a synthetic "no results" answer ONLY under the full corroboration conjunction
(`is_confirmed_empty`): an empty-result marker + an independent BROWSER render that
ALSO read empty + no 4xx/challenge anywhere + no subresource-block evidence + a
search-shaped URL. Any missing term keeps it a loud-ish failure. The walled-API
fake-empty (a benign "0 results" body whose data API was 403'd) stays a wall via
the subresource evidence — the case no text reader can catch.

Corroboration is by the browser, not jina: a thin HTTP 200 wins the tier loop, so
the free jina rung never runs on it — the browser escalation is the second
independent retrieval a thin page actually gets.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.models import CacheState, Confidence, FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state

# A styled empty-results page: 200, real chrome (clears the 32-char blank floor),
# under the 500-char extraction floor, matching an empty-result marker.
_EMPTY_HTML = (
    b"<html><body><main><h1>Search results</h1>"
    b"<p>No results found for your search. Try different keywords or browse categories.</p>"
    b"</main></body></html>"
)
# The browser-rendered empty body — > 32 visible chars so its regate is
# `length_floor`+`empty_result`, not `blank_page`.
_EMPTY_MD = "No results found for your search. Try different keywords or browse our categories."


def _http_tier(name: str, *, body: bytes = _EMPTY_HTML, verdict: Verdict = Verdict.ok, status_code: int = 200) -> object:
    class _T:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=body, content_type="text/html", status_code=status_code, final_url=url, verdict=verdict)

    _T.name = name  # type: ignore[attr-defined]
    return _T()


def _empty_browser(name: str, *, subresource_blocks: int = 0) -> object:
    """A browser that renders the empty-results body. `subresource_blocks > 0`
    models the walled-API fake-empty (a page XHR was 403'd during render)."""

    class _B:
        async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
            del state, backend, scroll, kwargs
            return TierResult(
                body=_EMPTY_HTML,
                content_type="text/html",
                status_code=200,
                final_url=url,
                from_browser=True,
                subresource_blocks=subresource_blocks,
                pre_rendered=Rendered(content_md=_EMPTY_MD, title="Search results"),
                verdict=Verdict.ok,
            )

    _B.name = name  # type: ignore[attr-defined]
    return _B()


def _install_empty_browser(monkeypatch: pytest.MonkeyPatch, *, subresource_blocks: int = 0) -> None:
    monkeypatch.setitem(REGISTRY, "browser", _empty_browser("browser", subresource_blocks=subresource_blocks))
    monkeypatch.setitem(REGISTRY, "browser_robust", _empty_browser("browser_robust", subresource_blocks=subresource_blocks))


@pytest.mark.asyncio
async def test_corroborated_empty_promotes_to_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """raw retrieves the empty body and the browser render corroborates it on a
    search URL, no wall evidence → promoted ok with a synthetic 'no results'."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_empty_browser(monkeypatch)

    fr = await fetch("https://shop.example/search?q=zzqnonexistent", state=make_default_state(), ask="find products", debug=True)

    assert fr.status == FetchStatus.ok
    assert fr.retrieval_incomplete is False
    hints = {h.code: h for h in fr.operator_hints}
    assert "content_empty" in hints and hints["content_empty"].severity == "info"
    assert "try_user_browser" not in hints
    assert "content_thin" not in hints

    ar = build_ask_response(fr, include_content=False, debug=False)
    assert ar.status == FetchStatus.ok
    assert ar.confidence == Confidence.low
    assert ar.answer and "no results" in ar.answer.lower()
    assert ar.thin_content is not None  # body attached to confirm


@pytest.mark.asyncio
async def test_no_browser_corroboration_is_not_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """No browser render corroborated the empty (browser unavailable) → the HTTP
    read alone does not promote; it stays a loud thin miss (empty_unverified)."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    # No browser installed → the real browser tier is unavailable → no regate-empty.

    fr = await fetch("https://shop.example/search?q=x", state=make_default_state(), debug=True)

    assert fr.status == FetchStatus.failed
    assert not any(h.code == "content_empty" for h in fr.operator_hints)
    assert any(h.code == "content_thin" for h in fr.operator_hints)  # empty_unverified
    assert not any(h.code == "try_user_browser" for h in fr.operator_hints)


@pytest.mark.asyncio
async def test_empty_behind_403_is_not_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 403 anywhere blocks promotion — an empty reading is not credible behind a
    refusal, even if the browser then renders empty."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw", body=b"", verdict=Verdict.connection_error, status_code=403))
    _install_empty_browser(monkeypatch)

    fr = await fetch("https://g2.example/search?q=crm", state=make_default_state(), debug=True)

    assert fr.status == FetchStatus.failed
    assert not any(h.code == "content_empty" for h in fr.operator_hints)


@pytest.mark.asyncio
async def test_non_search_url_is_not_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty reading of a non-search route is suspicious — not promoted."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_empty_browser(monkeypatch)

    fr = await fetch("https://shop.example/articles/how-to-buy", state=make_default_state(), debug=True)

    assert fr.status == FetchStatus.failed
    assert not any(h.code == "content_empty" for h in fr.operator_hints)
    assert any(h.code == "content_thin" for h in fr.operator_hints)


@pytest.mark.asyncio
async def test_promoted_empty_is_never_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A promoted empty keeps verdict `length_floor` (only the caller-facing status
    is ok), so cache_write declines it — a wrongly-promoted empty served from cache
    would be a REPEATING silent miss (ADR-0009). Proof: a second fetch of the same
    URL is still a cache MISS (nothing was stored the first time)."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_empty_browser(monkeypatch)

    state = make_default_state()
    await state.sqlite.ensure()
    url = "https://shop.example/search?q=neverstored"
    first = await fetch(url, state=state, debug=True)
    second = await fetch(url, state=state, debug=True)

    assert first.status == FetchStatus.ok
    assert any(h.code == "content_empty" for h in first.operator_hints)
    assert first.cache == CacheState.miss
    assert second.cache == CacheState.miss  # not a hit → the promoted empty was never cached


@pytest.mark.asyncio
async def test_walled_api_fake_empty_stays_a_wall(monkeypatch: pytest.MonkeyPatch) -> None:
    """The browser rendered a benign '0 results' body BUT watched its data API get
    403'd (subresource-block evidence) → a wall, never a promoted empty. The case no
    text reader can catch."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_empty_browser(monkeypatch, subresource_blocks=1)

    fr = await fetch("https://shop.example/search?q=x", state=make_default_state(), debug=True)

    assert fr.status == FetchStatus.failed
    assert fr.retrieval_incomplete is True
    assert not any(h.code == "content_empty" for h in fr.operator_hints)
    assert any(h.code == "try_user_browser" for h in fr.operator_hints)  # a wall, loud
