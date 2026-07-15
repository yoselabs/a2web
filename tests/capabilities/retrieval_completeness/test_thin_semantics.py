"""End-to-end: thin-but-retrieved 200 semantics (thin-not-wall).

A retrieved HTTP 200 that renders thin with NO wall evidence (an empty search
result / minimal page) must be reported as an honest WARNING with the tiny body
attached — NEVER the critical anti-bot `try_user_browser` klaxon (the trendyol
soft-404 incident). A thin body DOWNSTREAM of a real wall stays a wall.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests.conftest import make_default_state

# A styled empty-results page: HTTP 200, real chrome text (clears the blank-page
# floor), but under the 500-char extraction floor — the shape of "no matches".
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


@pytest.mark.asyncio
async def test_thin_200_is_thin_unverified_not_walled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean thin 200 → status failed, `content_thin` WARNING, retrieval
    incomplete, and crucially NO critical `try_user_browser`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    result = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert not any(h.code == "try_user_browser" for h in result.operator_hints), "a thin 200 is not an anti-bot wall"
    hints = {h.code: h for h in result.operator_hints}
    assert "content_thin" in hints
    assert hints["content_thin"].severity == "warning"
    assert result.retrieval_incomplete is True


@pytest.mark.asyncio
async def test_thin_200_attaches_body_to_ask_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retrieved thin body rides `thin_content` on the ask envelope so the
    blind caller can read it (ADR-0015) — even without include_content."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=_EMPTY_RESULTS_HTML))
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    fr = await fetch("https://shop.example/sr?q=zzzqqxnonexistent", state=make_default_state(), ask="what did I find?", debug=True)
    ar = build_ask_response(fr, include_content=False, debug=False)

    assert ar.thin_content is not None
    assert "bulunamadi" in ar.thin_content.lower() or "no products matched" in ar.thin_content.lower()


@pytest.mark.asyncio
async def test_thin_downstream_of_wall_stays_walled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A thin body that lands AFTER positive wall evidence (an anti-bot render
    that came back thin) stays a wall → critical `try_user_browser`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))

    # raw fingerprints an anti-bot wall (Turnstile marker in the body) → hard-wall
    # gate evidence enters the log.
    turnstile = b'<html><body><div class="cf-turnstile" data-sitekey="x"></div></body></html>'
    monkeypatch.setitem(REGISTRY, "raw", _html_tier("raw", body=turnstile, verdict=Verdict.ok))
    # jina then returns a marker-less thin body (last gate = length_floor).
    monkeypatch.setitem(REGISTRY, "jina", _html_tier("jina", body=_EMPTY_RESULTS_HTML))

    result = await fetch("https://walled.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    # The whole-log scan finds the Turnstile hard wall → wall, not thin_unverified.
    assert any(h.code == "try_user_browser" for h in result.operator_hints)
    assert not any(h.code == "content_thin" for h in result.operator_hints)
