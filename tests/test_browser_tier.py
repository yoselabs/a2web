"""BrowserTier — Camoufox-rendered fetch, graceful when dep missing."""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY


@pytest.fixture(autouse=True)
def _restore_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo conftest's UnavailableBrowserTier — these tests want the real tier."""
    from a2web.tiers.browser import BrowserTier

    monkeypatch.setitem(REGISTRY, "browser", BrowserTier())


def _make_state() -> AppState:
    return AppState(settings=AppSettings())


@pytest.mark.asyncio
async def test_disabled_returns_unavailable() -> None:
    state = _make_state()
    state.settings = AppSettings(browser_enabled=False)
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=state)
    assert result.verdict == Verdict.connection_error
    hint = result.tier_extras["operator_hint"]
    assert hint["code"] == "browser_unavailable"


@pytest.mark.asyncio
async def test_import_error_yields_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When camoufox isn't installed, return graceful operator hint."""
    real_import = builtins.__import__

    def _fake_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0):
        if name == "camoufox.async_api" or name.startswith("camoufox"):
            raise ImportError("No module named 'camoufox'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    state = _make_state()
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=state)
    assert result.verdict == Verdict.connection_error
    assert result.tier_extras["operator_hint"]["code"] == "browser_unavailable"
    assert "camoufox" in result.tier_extras["operator_hint"]["message"].lower()


@pytest.mark.asyncio
async def test_successful_fetch_via_stub_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the BrowserPool to verify the tier's HTML→markdown pipeline."""

    class _StubPage:
        url = "https://example.com/final"

        async def goto(self, url: str, wait_until: str = "networkidle") -> Any:
            del url, wait_until

            class _Resp:
                status = 200

            return _Resp()

        async def content(self) -> str:
            return "<html><body><h1>Hello</h1><p>" + ("Body content. " * 80) + "</p></body></html>"

        async def close(self) -> None:
            return None

    class _StubPoolCtx:
        async def __aenter__(self) -> _StubPage:
            return _StubPage()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _StubPool:
        def acquire(self, url: str) -> _StubPoolCtx:
            del url
            return _StubPoolCtx()

        async def close(self) -> None:
            return None

    async def _fake_ensure(state: AppState) -> _StubPool:
        del state
        return _StubPool()

    monkeypatch.setattr("a2web.state.ensure_browser_pool", _fake_ensure)

    state = _make_state()
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=state)

    assert result.verdict == Verdict.ok
    assert result.tier_extras["from_browser"] is True
    assert result.tier_extras["js_executed"] is True
    assert "Body content" in result.tier_extras["pre_rendered"]["content_md"]
    assert result.final_url == "https://example.com/final"


@pytest.mark.asyncio
async def test_navigation_timeout_yields_timeout_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    class _SlowPage:
        url = "https://example.com/"

        async def goto(self, url: str, wait_until: str = "networkidle") -> Any:
            del url, wait_until
            await asyncio.sleep(10.0)

        async def content(self) -> str:
            return ""

        async def close(self) -> None:
            return None

    class _StubPoolCtx:
        async def __aenter__(self) -> _SlowPage:
            return _SlowPage()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _StubPool:
        def acquire(self, url: str) -> _StubPoolCtx:
            del url
            return _StubPoolCtx()

        async def close(self) -> None:
            return None

    async def _fake_ensure(state: AppState) -> _StubPool:
        del state
        return _StubPool()

    monkeypatch.setattr("a2web.state.ensure_browser_pool", _fake_ensure)

    state = _make_state()
    state.settings = AppSettings(browser_page_budget_s=1)
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://slow.example/", state=state)

    assert result.verdict == Verdict.timeout
    assert result.tier_extras["js_executed"] is True


def test_browser_in_registry_not_in_tier_order() -> None:
    from a2web.tiers import REGISTRY as REAL_REGISTRY
    from a2web.tiers import TIER_ORDER

    assert "browser" in REAL_REGISTRY
    assert "browser" not in TIER_ORDER
