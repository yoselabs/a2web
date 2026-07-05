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

# A fat shell: trafilatura keeps >500 chars, so it passes the length floor and
# reaches answer extraction — where only the LLM notices the answer isn't there.
_SHELL_HTML = ("<html><body><article>" + ("Boilerplate shell chrome that reads like prose. " * 25) + "</article></body></html>").encode()

_OBSTACLE_EMPTY = json.dumps(
    {"answer": "A fluent but unfounded answer.", "structural_form": "article", "shape": "prose", "obstacle": "empty"}
)
_CLEAN_ANSWER = json.dumps(
    {"answer": "The real answer from the rendered page.", "structural_form": "article", "shape": "prose"}
)


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
