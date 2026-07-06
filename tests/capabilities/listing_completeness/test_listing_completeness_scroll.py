"""listing-completeness Slice 2: bounded scroll-to-complete.

When `complete_listings` is enabled and a partial listing was served by a
non-scrolling tier, the orchestrator dispatches ONE scrolling render (sharing
the single paid-dispatch cap), re-counts, and drops the `listing_partial`
signal iff the listing is now complete — else the signal stands (loud miss).
A broad-search oracle above `listing_scroll_max` steers instead of scrolling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from a2kit.testing import lazy

from a2web.fetcher import _listing_wants_render, fetch
from a2web.llm_resource import LlmExtractorResource
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from a2web.tiers.zyte import _zyte_extract_request
from tests.capabilities.listing_completeness.test_listing_completeness import _listing_html
from tests.conftest import make_default_state

_LISTING_ANSWER = json.dumps({"answer": "The aerators.", "structural_form": "listing", "shape": "records"})


# --------------------------------------------------------------------- #
# Zyte scroll actions — pure request builder
# --------------------------------------------------------------------- #


def test_zyte_request_raw_has_no_actions() -> None:
    req = _zyte_extract_request("https://x/y", raw=True, scroll=True, scroll_cap=4)
    assert req == {"url": "https://x/y", "httpResponseBody": True}


def test_zyte_request_browser_no_scroll_has_no_actions() -> None:
    req = _zyte_extract_request("https://x/y", raw=False, scroll=False, scroll_cap=4)
    assert "actions" not in req
    assert req["browserHtml"] is True


def test_zyte_request_browser_scroll_adds_bounded_actions() -> None:
    req = _zyte_extract_request("https://x/y", raw=False, scroll=True, scroll_cap=3)
    actions = req["actions"]
    # scroll_cap scroll+wait pairs.
    assert len(actions) == 6
    assert any(a.get("action") == "scrollBottom" for a in actions)


# --------------------------------------------------------------------- #
# _listing_wants_render predicate
# --------------------------------------------------------------------- #


@dataclass
class _Fc:
    ask: str | None = "q"
    items_total: int | None = 40
    paid_dispatches: int = 0
    tier_used: str = "raw"


def _settings(**kw: object) -> AppSettings:
    return AppSettings(complete_listings=True, listing_scroll_max=200, **kw)


class TestListingWantsRender:
    def test_fires_on_enabled_partial_ask(self) -> None:
        assert _listing_wants_render(_Fc(), settings=_settings())

    def test_disabled_does_not_fire(self) -> None:
        assert not _listing_wants_render(_Fc(), settings=AppSettings(complete_listings=False))

    def test_no_ask_does_not_fire(self) -> None:
        assert not _listing_wants_render(_Fc(ask=None), settings=_settings())

    def test_not_partial_does_not_fire(self) -> None:
        assert not _listing_wants_render(_Fc(items_total=None), settings=_settings())

    def test_spent_budget_does_not_fire(self) -> None:
        assert not _listing_wants_render(_Fc(paid_dispatches=1), settings=_settings())

    def test_js_executed_tier_does_not_fire(self) -> None:
        for tier in ("jina", "browser", "browser_robust"):
            assert not _listing_wants_render(_Fc(tier_used=tier), settings=_settings())

    def test_oracle_above_ceiling_steers_not_scrolls(self) -> None:
        assert not _listing_wants_render(_Fc(items_total=5000), settings=_settings())


# --------------------------------------------------------------------- #
# Fetch-level scroll-to-complete behaviour
# --------------------------------------------------------------------- #


class _PartialListingRawTier:
    """Raw tier serving a 31-of-40 partial listing (infinite-scroll sample)."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=_listing_html(31, oracle_jsonld=40),
            content_type="text/html",
            status_code=200,
            final_url=url,
            verdict=Verdict.ok,
        )


class _ScrollZyteStub:
    """Paid render that (after scrolling) returns the FULL 40-record listing."""

    name = "zyte"

    def __init__(self, records: int) -> None:
        self._body = _listing_html(records, oracle_jsonld=40)
        self.scroll_seen: bool | None = None

    async def fetch(self, url: str, *, state: AppState, scroll: bool = False, **kwargs: object) -> TierResult:
        del state, kwargs
        self.scroll_seen = scroll
        return TierResult(
            body=self._body,
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md="rendered listing"),
            verdict=Verdict.ok,
        )


def _extractor(state: AppState) -> LlmExtractorResource:
    class _P:
        name = "stub"

        async def complete(self, *, system: object, user: object, model: str, **_: object) -> object:
            from a2web.packages.llm_extract import ProviderResponse

            return ProviderResponse(text=_LISTING_ANSWER, model=model, prompt_tokens=100, completion_tokens=10, cost_usd=0.0, latency_ms=10)

    return LlmExtractorResource(state.settings, state.sqlite, lazy(_P()))


async def _ask_fetch(state: AppState, url: str = "https://shop.example/search?q=aerator"):
    return await fetch(url, state=state, ask="List the aerators.", llm_extractor=lazy(_extractor(state)), debug=True)


@pytest.mark.asyncio
async def test_scroll_completes_listing_and_clears_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _ScrollZyteStub(records=40)
    monkeypatch.setitem(REGISTRY, "raw", _PartialListingRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", stub)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=_settings())

    result = await _ask_fetch(state)

    assert stub.scroll_seen is True  # the render was asked to scroll
    assert any(d.step == "zyte" for d in result.diagnostics)
    # Completed to 40/40 → the partial signal is dropped.
    assert result.items_loaded is None
    assert result.items_total is None
    assert "listing_partial" not in [h.code for h in result.operator_hints]


@pytest.mark.asyncio
async def test_scroll_still_short_keeps_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # The render only reached 34 of 40 (virtualised / capped) → still partial.
    stub = _ScrollZyteStub(records=34)
    monkeypatch.setitem(REGISTRY, "raw", _PartialListingRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", stub)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=_settings())

    result = await _ask_fetch(state)

    assert result.items_total == 40
    assert result.items_loaded == 34  # updated count, still short
    assert "listing_partial" in [h.code for h in result.operator_hints]


@pytest.mark.asyncio
async def test_no_paid_tier_keeps_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _PartialListingRawTier())
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=_settings())

    result = await _ask_fetch(state)

    # No render possible → the loud partial signal stands (never-silently-miss).
    assert result.items_loaded == 31
    assert result.items_total == 40
    assert "listing_partial" in [h.code for h in result.operator_hints]


@pytest.mark.asyncio
async def test_disabled_does_not_scroll(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _ScrollZyteStub(records=40)
    monkeypatch.setitem(REGISTRY, "raw", _PartialListingRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", stub)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    state = make_default_state(settings=AppSettings())  # complete_listings defaults off

    result = await _ask_fetch(state)

    assert stub.scroll_seen is None  # never dispatched
    assert not any(d.step == "zyte" for d in result.diagnostics)
    assert result.items_loaded == 31  # Slice 1 signal stands
    assert "listing_partial" in [h.code for h in result.operator_hints]
