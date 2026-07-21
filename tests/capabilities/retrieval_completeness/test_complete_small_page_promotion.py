"""End-to-end: corroborated complete SMALL page → ok promotion.

The non-empty sibling of `test_empty_promotion.py` (empty-vs-wall-discrimination).
A retrieved thin 200 that is a genuinely small COMPLETE page — not an empty result
set, not a wall — is promoted to `status: ok` and the extractor runs on the real
body, ONLY under the `is_complete_small_page` conjunction: an HTTP body + an
independent BROWSER render that agreed the page is small (thin, non-empty, no wall)
+ no 4xx/challenge + no subresource-block evidence + no hard-wall evidence. Unlike
the empty promotion there is NO search-shaped-URL term and NO synthetic answer.

The false-positive asymmetry holds: any wall evidence (a challenged subresource, a
hard-wall marker) forbids the promotion, so a walled 230-char shell stays a loud
`content_thin` failure — never a confident answer (ADR-0009).
"""

from __future__ import annotations

import pytest
from a2kit.testing import lazy

from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.llm_resource import LlmExtractorResource
from a2web.models import CacheState, Confidence, FetchStatus, Verdict
from a2web.packages.llm_extract import ProviderResponse
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state

# A tiny COMPLETE page: 200, real visible text (clears the 32-char blank floor),
# under the 500-char extraction floor, with NO empty-result marker — the example.com
# shape. Gate → bare `length_floor` + `thin_fallthrough`.
_SMALL_HTML = (
    b"<html><body><main>"
    b"<p>This domain is for use in documentation examples without needing permission. "
    b"Avoid use in operations. Learn more.</p>"
    b"</main></body></html>"
)
_SMALL_MD = "This domain is for use in documentation examples without needing permission. Avoid use in operations. Learn more."


def _http_tier(name: str, *, body: bytes = _SMALL_HTML, verdict: Verdict = Verdict.ok, status_code: int = 200) -> object:
    class _T:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=body, content_type="text/html", status_code=status_code, final_url=url, verdict=verdict)

    _T.name = name  # type: ignore[attr-defined]
    return _T()


def _small_browser(name: str, *, subresource_blocks: int = 0) -> object:
    """A browser that renders the same small body. `subresource_blocks > 0` models a
    walled-API fake-thin (a page XHR was 403'd during render) — a wall, not a page."""

    class _B:
        async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
            del state, backend, scroll, kwargs
            return TierResult(
                body=_SMALL_HTML,
                content_type="text/html",
                status_code=200,
                final_url=url,
                from_browser=True,
                subresource_blocks=subresource_blocks,
                pre_rendered=Rendered(content_md=_SMALL_MD, title="Example Domain"),
                verdict=Verdict.ok,
            )

    _B.name = name  # type: ignore[attr-defined]
    return _B()


def _install_small_browser(monkeypatch: pytest.MonkeyPatch, *, subresource_blocks: int = 0) -> None:
    monkeypatch.setitem(REGISTRY, "browser", _small_browser("browser", subresource_blocks=subresource_blocks))
    monkeypatch.setitem(REGISTRY, "browser_robust", _small_browser("browser_robust", subresource_blocks=subresource_blocks))


class _StubProvider:
    """LLM stub returning a fixed answer — proves the extractor RAN on the body."""

    name = "stub"

    def __init__(self, *, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system, user
        self.calls += 1
        return ProviderResponse(text=self.answer, model=model, prompt_tokens=80, completion_tokens=12, cost_usd=0.0, latency_ms=9)


def _extractor(state: AppState, *, answer: str) -> tuple[LlmExtractorResource, _StubProvider]:
    provider = _StubProvider(answer=answer)
    return LlmExtractorResource(state.settings, state.sqlite, lazy(provider)), provider


@pytest.mark.asyncio
async def test_corroborated_small_page_promotes_and_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """raw retrieves a tiny complete body, the browser render agrees it is small (no
    wall), and the extractor answers from it → status ok, extraction ran, confidence
    low. The example.com case — a complete tiny page must answer, not fail."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_small_browser(monkeypatch)
    state = make_default_state()
    extractor_res, provider = _extractor(state, answer="This is a reserved example domain for documentation.")

    fr = await fetch(
        "https://example.com/",
        state=state,
        ask="what is this page about",
        llm_extractor=lazy(extractor_res),
        debug=True,
    )

    assert fr.status == FetchStatus.ok
    assert fr.retrieval_incomplete is False
    assert provider.calls == 1  # extraction RAN on the real body
    assert fr.extracted_answer == "This is a reserved example domain for documentation."
    hints = {h.code for h in fr.operator_hints}
    assert "content_thin" not in hints  # not a failure
    assert "try_user_browser" not in hints  # not a wall

    ar = build_ask_response(fr, include_content=False, debug=False)
    assert ar.status == FetchStatus.ok
    assert ar.confidence == Confidence.low  # still a thin page — honest hedge
    assert ar.answer == "This is a reserved example domain for documentation."


@pytest.mark.asyncio
async def test_small_page_burns_exactly_one_browser_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare thin fallthrough gets exactly ONE browser render (the corroborating
    witness), not two — the second would only re-confirm the page is small."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))

    renders = {"n": 0}
    orig = _small_browser("browser")

    class _CountingBrowser:
        name = "browser"

        async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
            renders["n"] += 1
            return await orig.fetch(url, state=state, backend=backend, scroll=scroll, **kwargs)  # type: ignore[attr-defined]

    monkeypatch.setitem(REGISTRY, "browser", _CountingBrowser())
    monkeypatch.setitem(REGISTRY, "browser_robust", _CountingBrowser())
    state = make_default_state()
    extractor_res, _ = _extractor(state, answer="A reserved example domain.")

    await fetch("https://example.com/", state=state, ask="what is this", llm_extractor=lazy(extractor_res), debug=True)

    assert renders["n"] == 1  # exactly the one witness render, not two


@pytest.mark.asyncio
async def test_thin_page_with_subresource_wall_is_not_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The browser rendered the same thin body BUT watched a data-API XHR get 403'd
    (subresource-block evidence) → a wall, never a promoted small page. The
    false-positive asymmetry: an ambiguous thin page errs toward the wall."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_small_browser(monkeypatch, subresource_blocks=1)
    state = make_default_state()
    extractor_res, provider = _extractor(state, answer="should not be surfaced")

    fr = await fetch("https://example.com/", state=state, ask="what is this", llm_extractor=lazy(extractor_res), debug=True)

    assert fr.status == FetchStatus.failed
    assert fr.retrieval_incomplete is True
    assert provider.calls == 0  # extraction never ran — verdict never reached ok/promoted
    assert any(h.code == "try_user_browser" for h in fr.operator_hints)  # a wall, loud


@pytest.mark.asyncio
async def test_no_browser_corroboration_is_not_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """No browser render corroborated the thinness (browser unavailable) → the HTTP
    read alone does not promote; it stays a loud thin miss (content_thin)."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    # No browser installed → the real browser tier is unavailable → no thin regate.
    state = make_default_state()
    extractor_res, _ = _extractor(state, answer="unused")

    fr = await fetch("https://example.com/", state=state, ask="what is this", llm_extractor=lazy(extractor_res), debug=True)

    assert fr.status == FetchStatus.failed
    assert any(h.code == "content_thin" for h in fr.operator_hints)
    assert "try_user_browser" not in {h.code for h in fr.operator_hints}  # thin, not a wall


@pytest.mark.asyncio
async def test_promoted_small_page_is_never_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A promoted small page keeps verdict `length_floor` (only the caller-facing
    status is ok), so cache_write declines it (design decision 1: wire-only). Proof:
    a second fetch of the same URL is still a cache MISS."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _http_tier("raw"))
    _install_small_browser(monkeypatch)

    state = make_default_state()
    await state.sqlite.ensure()
    extractor_res, _ = _extractor(state, answer="A reserved example domain.")
    url = "https://example.com/never-stored"

    first = await fetch(url, state=state, ask="what is this", llm_extractor=lazy(extractor_res), debug=True)
    second = await fetch(url, state=state, ask="what is this", llm_extractor=lazy(extractor_res), debug=True)

    assert first.status == FetchStatus.ok
    assert first.cache == CacheState.miss
    assert second.cache == CacheState.miss  # not a hit → the promoted small page was never cached
