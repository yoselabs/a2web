"""Orchestrator browser escalation: gate suggested_tier=browser → dispatch."""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state

_ANUBIS_HTML = b"<html><head><title>Checking...</title></head><body><script src='/.well-known/anubis/check.js'></script></body></html>"


class _AnubisRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=_ANUBIS_HTML,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


class _RecoveringBrowserTier:
    name = "browser"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state
        markdown = "# Real Article\n\n" + ("Real body content. " * 80)
        return TierResult(
            body=markdown.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            from_browser=True,
            js_executed=True,
            pre_rendered=Rendered(content_md=markdown, title="Real Article"),
            verdict=Verdict.ok,
        )


def _make_state() -> AppState:
    return make_default_state()


@pytest.mark.asyncio
async def test_anubis_triggers_browser_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _RecoveringBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    # debug=True — inspect diagnostics trace (v0.3 wire-default omits it).
    result = await fetch("https://anubis.example/", state=_make_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "browser"
    assert result.title == "Real Article"
    # Browser-rendered results SHOULD cache (unlike archive).
    assert any(d.step == "browser" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_browser_unavailable_surfaces_operator_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """When browser tier is unavailable, original verdict stands + hint surfaces."""
    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    # conftest's _UnavailableBrowserTier is in place
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://anubis.example/", state=_make_state())

    assert result.status == FetchStatus.failed
    # Operator hint surfaces
    assert any(h.code == "browser_unavailable" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_browser_dispatch_capped_at_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pathological case: browser also returns blocked content. No second dispatch."""

    dispatches = {"n": 0}

    class _StillBlockedBrowserTier:
        name = "browser"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state
            dispatches["n"] += 1
            # Return content that will re-trigger anubis on re-gate
            blocked_md = "anubis check pending"
            return TierResult(
                body=blocked_md.encode("utf-8"),
                content_type="text/html",
                status_code=200,
                final_url=url,
                from_browser=True,
                js_executed=True,
                pre_rendered=Rendered(content_md=blocked_md),
                verdict=Verdict.ok,
            )

    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _StillBlockedBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://anubis.example/", state=_make_state())

    assert dispatches["n"] == 1
    assert result.status == FetchStatus.failed
