"""Obstacle-driven render escalation — obstacle-driven-render-escalation.

When the `ask` extractor reports `obstacle ∈ {empty, blocked}` over content that
passed the gate (a fat SPA shell), the orchestrator dispatches ONE paid render,
re-extracts the answer over the real content, and only declares
`retrieval_incomplete` if the render can't be done or doesn't help. Bounded to one
render + one extra LLM call; `paywalled`/`error` never trigger a render.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from a2kit.testing import lazy

from a2web.fetcher import _obstacle_wants_render, fetch
from a2web.fetcher_response import build_ask_response
from a2web.llm_resource import LlmExtractorResource
from a2web.models import Confidence, Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state

# A fat SPA shell: >500 chars of chrome (passes the length floor) PLUS
# unrendered-SPA markers (a root mount + a script), so the false-positive guard
# recognizes that a render could add content. Only the LLM notices the answer
# isn't there.
_SHELL_HTML = (
    '<html><head><script src="/static/app.js"></script></head><body>'
    '<div id="root"></div>'
    "<article>" + ("Boilerplate shell chrome that reads like prose. " * 25) + "</article>"
    "</body></html>"
).encode()

# A complete static page (like an RFC / a book): substantial real prose, NO SPA
# markers — rendering it again cannot add the missing answer, so the guard must
# NOT trigger a render even when the extractor reports obstacle=empty.
_STATIC_PROSE = "A complete static document with real prose and no client-render markers. " * 20
_STATIC_HTML = ("<html><body><article>" + _STATIC_PROSE + "</article></body></html>").encode()

# An SSR framework page (Next/Nuxt): carries SPA mount markers YET already
# contains substantial content (>2000 extracted chars). The answer's absence is
# real — a render can't add it, so the ceiling must suppress the render even
# though the markers match. Mirrors the live rfc-editor.org (Nuxt) case.
_SSR_PROSE = "Substantial server-rendered documentation content in full. " * 60
_SSR_HTML = (
    '<html><head><script src="/_nuxt/app.js"></script></head><body>'
    '<div id="__nuxt"><article>' + _SSR_PROSE + "</article></div></body></html>"
).encode()

_OBSTACLE_EMPTY = json.dumps(
    {"answer": "A fluent but unfounded answer.", "structural_form": "article", "shape": "prose", "obstacle": "empty"}
)
_CLEAN_ANSWER = json.dumps({"answer": "The real answer from the rendered page.", "structural_form": "article", "shape": "prose"})


# --------------------------------------------------------------------- #
# Predicate — _obstacle_wants_render
# --------------------------------------------------------------------- #


@dataclass
class _Rt:
    obstacle: str | None


@dataclass
class _Fc:
    ask: str | None
    routing: object
    paid_dispatches: int
    tier_used: str = "raw"
    body: bytes = _SHELL_HTML  # SPA-shell markers by default → render-worthy
    content_md: str = "thin shell content"  # below the ceiling by default


class TestObstacleWantsRender:
    def test_empty_obstacle_ask_unspent_budget(self) -> None:
        assert _obstacle_wants_render(_Fc(ask="q", routing=_Rt("empty"), paid_dispatches=0))

    def test_blocked_obstacle_fires(self) -> None:
        assert _obstacle_wants_render(_Fc(ask="q", routing=_Rt("blocked"), paid_dispatches=0))

    def test_paywalled_and_error_do_not_fire(self) -> None:
        assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt("paywalled"), paid_dispatches=0))
        assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt("error"), paid_dispatches=0))

    def test_no_obstacle_does_not_fire(self) -> None:
        assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt(None), paid_dispatches=0))

    def test_no_ask_does_not_fire(self) -> None:
        assert not _obstacle_wants_render(_Fc(ask=None, routing=_Rt("empty"), paid_dispatches=0))

    def test_no_routing_does_not_fire(self) -> None:
        assert not _obstacle_wants_render(_Fc(ask="q", routing=None, paid_dispatches=0))

    def test_spent_paid_budget_suppresses(self) -> None:
        # A prior gate/handler render already spent the budget — don't pay twice.
        assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt("empty"), paid_dispatches=1))

    def test_js_executed_tier_suppresses(self) -> None:
        # jina / browser already executed JS — a re-render returns the same content.
        for tier in ("jina", "browser", "browser_robust"):
            assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt("empty"), paid_dispatches=0, tier_used=tier))

    def test_static_page_without_spa_markers_suppresses(self) -> None:
        # A thin static page with no SPA markers → a render cannot add the
        # missing answer, so don't pay for one.
        assert not _obstacle_wants_render(_Fc(ask="q", routing=_Rt("empty"), paid_dispatches=0, body=_STATIC_HTML))

    def test_substantial_content_suppresses(self) -> None:
        # The SSR false-positive (Next/Nuxt): the body has SPA mount markers but
        # substantial content was already retrieved → the page is complete, the
        # answer's absence is real, a render is pure waste.
        fc = _Fc(ask="q", routing=_Rt("empty"), paid_dispatches=0, body=_SHELL_HTML, content_md="x" * 2500)
        assert not _obstacle_wants_render(fc)

    def test_thin_spa_shell_with_markers_fires(self) -> None:
        fc = _Fc(ask="q", routing=_Rt("empty"), paid_dispatches=0, body=_SHELL_HTML, content_md="thin shell")
        assert _obstacle_wants_render(fc)


# --------------------------------------------------------------------- #
# Fetch-level phase behavior
# --------------------------------------------------------------------- #


class _ShellRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_SHELL_HTML, content_type="text/html", status_code=200, final_url=url, verdict=Verdict.ok)


class _RenderPaidTier:
    """A paid tier that renders real content (markdown-native, like Firecrawl/Zyte md)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._md = "# Rendered\n\n" + ("The real rendered answer content. " * 30)

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=self._md.encode(),
            content_type="text/markdown",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=self._md, title="Rendered"),
            verdict=Verdict.ok,
        )


class _SequencedProvider:
    """Returns each canned response in order (obstacle first, clean after render)."""

    name = "stub"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    async def complete(self, *, system: object, user: object, model: str, **_: object) -> object:
        from a2web.packages.llm_extract import ProviderResponse

        text = self._responses[min(len(self.calls), len(self._responses) - 1)]
        self.calls.append({"system": system, "user": user, "model": model})
        return ProviderResponse(text=text, model=model, prompt_tokens=200, completion_tokens=20, cost_usd=0.0005, latency_ms=120)


def _extractor(state: AppState, provider: _SequencedProvider) -> LlmExtractorResource:
    return LlmExtractorResource(state.settings, state.sqlite, lazy(provider))


def _install(monkeypatch: pytest.MonkeyPatch, *, with_paid: bool) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    if with_paid:
        monkeypatch.setitem(REGISTRY, "zyte", _RenderPaidTier("zyte"))
    else:
        monkeypatch.delitem(REGISTRY, "zyte", raising=False)
        monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)


@pytest.mark.asyncio
async def test_empty_obstacle_renders_and_reextracts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, with_paid=True)
    state = make_default_state(settings=AppSettings())
    provider = _SequencedProvider([_OBSTACLE_EMPTY, _CLEAN_ANSWER])

    result = await fetch(
        "https://spa.example/?q=claude",
        state=state,
        ask="What is the answer?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    # Re-extracted after the render: two LLM calls, the clean answer wins.
    assert len(provider.calls) == 2
    assert result.extracted_answer == "The real answer from the rendered page."
    assert result.routing is not None and result.routing.obstacle is None
    assert any(d.step == "zyte" for d in result.diagnostics)
    # Product surface: not flagged incomplete once the render cleared the obstacle.
    ask = build_ask_response(result, include_content=False, debug=False)
    assert ask.retrieval_incomplete is False


@pytest.mark.asyncio
async def test_empty_obstacle_without_paid_flags_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, with_paid=False)
    state = make_default_state(settings=AppSettings())
    provider = _SequencedProvider([_OBSTACLE_EMPTY])

    result = await fetch(
        "https://spa.example/?q=claude",
        state=state,
        ask="What is the answer?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    # No paid tier keyed → no render, no re-extraction; the obstacle survives.
    assert len(provider.calls) == 1
    assert result.routing is not None and result.routing.obstacle == "empty"
    ask = build_ask_response(result, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True
    assert ask.confidence == Confidence.low
    assert "retrieval_incomplete" in [h.code for h in ask.operator_hints]


@pytest.mark.asyncio
async def test_paywalled_obstacle_does_not_render(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, with_paid=True)
    state = make_default_state(settings=AppSettings())
    paywalled = json.dumps({"answer": "Behind a paywall.", "structural_form": "article", "shape": "prose", "obstacle": "paywalled"})
    provider = _SequencedProvider([paywalled])

    result = await fetch(
        "https://paywall.example/article",
        state=state,
        ask="What is the answer?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    # paywalled never triggers a render — one LLM call, no zyte dispatch.
    assert len(provider.calls) == 1
    assert not any(d.step == "zyte" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_render_that_adds_nothing_keeps_obstacle(monkeypatch: pytest.MonkeyPatch) -> None:
    """A paid tier that returns the SAME shell content → no re-extraction, obstacle stands."""

    class _NoOpPaidTier:
        name = "zyte"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            # verdict not ok / no pre_rendered → _escalate_paid installs nothing.
            return TierResult(body=b"", content_type="text/markdown", status_code=503, final_url=url, verdict=Verdict.connection_error)

    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _NoOpPaidTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=AppSettings())
    provider = _SequencedProvider([_OBSTACLE_EMPTY])

    result = await fetch(
        "https://spa.example/?q=x",
        state=state,
        ask="What is the answer?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    # Render dispatched but produced nothing new → no second LLM call, obstacle survives.
    assert len(provider.calls) == 1
    assert result.routing is not None and result.routing.obstacle == "empty"
    ask = build_ask_response(result, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True


class _StaticRawTier:
    """A complete static page (no SPA markers) — a render can't add content."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_STATIC_HTML, content_type="text/html", status_code=200, final_url=url, verdict=Verdict.ok)


@pytest.mark.asyncio
async def test_static_page_obstacle_does_not_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """False-positive fix (the RFC case): a complete static page with no SPA
    markers reporting obstacle=empty must NOT trigger a paid render — the answer
    genuinely isn't there and a render can't add it."""
    monkeypatch.setitem(REGISTRY, "raw", _StaticRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _RenderPaidTier("zyte"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=AppSettings())
    provider = _SequencedProvider([_OBSTACLE_EMPTY])

    result = await fetch(
        "https://spec.example/doc",
        state=state,
        ask="What is the cookie recipe?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    # No render, one LLM call, obstacle survives → incomplete (loud miss, no cost).
    assert not any(d.step == "zyte" for d in result.diagnostics)
    assert len(provider.calls) == 1
    ask = build_ask_response(result, include_content=False, debug=False)
    assert ask.retrieval_incomplete is True


class _SsrRawTier:
    """An SSR framework page: SPA markers + substantial content already present."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_SSR_HTML, content_type="text/html", status_code=200, final_url=url, verdict=Verdict.ok)


@pytest.mark.asyncio
async def test_ssr_page_with_markers_but_full_content_does_not_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rfc-editor.org (Nuxt) case: SPA mount markers are present, but the
    page already carries its full content. `obstacle: empty` (the answer isn't
    there) must NOT trigger a render — the content ceiling suppresses it."""
    monkeypatch.setitem(REGISTRY, "raw", _SsrRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _RenderPaidTier("zyte"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=AppSettings())
    provider = _SequencedProvider([_OBSTACLE_EMPTY])

    result = await fetch(
        "https://ssr.example/doc",
        state=state,
        ask="What is the cookie recipe?",
        llm_extractor=lazy(_extractor(state, provider)),
        debug=True,
    )

    assert not any(d.step == "zyte" for d in result.diagnostics)  # ceiling suppressed the render
    assert len(provider.calls) == 1
