"""BrowserTier — delegates to a BrowserBackend; maps RenderOutcome → TierResult."""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from a2web.models import Verdict
from a2web.packages.browser_backends import PlaywrightBackend, RenderedPage, RenderOutcome, camoufox_launcher
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY
from tests.conftest import make_default_state


@pytest.fixture(autouse=True)
def _restore_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo conftest's UnavailableBrowserTier — these tests want the real tier."""
    from a2web.tiers.browser import BrowserTier

    monkeypatch.setitem(REGISTRY, "browser", BrowserTier())


def _make_state() -> AppState:
    return make_default_state()


def _real_backend() -> PlaywrightBackend:
    """A real PlaywrightBackend with the Camoufox launcher (no Camoufox launches
    unless `render` is actually called and the import succeeds)."""
    return PlaywrightBackend(camoufox_launcher, name="camoufox")


class _StubBackend:
    """Returns a preset `RenderedPage` — exercises the tier's outcome mapping."""

    name = "stub"

    def __init__(self, page: RenderedPage) -> None:
        self._page = page

    async def render(self, url: str, *, cookies: Any, budget_s: float, js_heavy: bool) -> RenderedPage:
        del url, cookies, budget_s, js_heavy
        return self._page

    async def __aenter__(self) -> _StubBackend:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.mark.asyncio
async def test_disabled_returns_unavailable() -> None:
    state = _make_state()
    state.settings = AppSettings(browser_enabled=False)
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=state, backend=_real_backend())
    assert result.verdict == Verdict.connection_error
    assert result.operator_hint.code == "browser_unavailable"


@pytest.mark.asyncio
async def test_import_error_yields_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When camoufox isn't installed, render() reports unavailable → hint."""
    real_import = builtins.__import__

    def _fake_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0):
        if name == "camoufox.async_api" or name.startswith("camoufox"):
            raise ImportError("No module named 'camoufox'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    state = _make_state()
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=state, backend=_real_backend())
    assert result.verdict == Verdict.connection_error
    assert result.operator_hint.code == "browser_unavailable"
    assert "camoufox" in result.operator_hint.message.lower()


@pytest.mark.asyncio
async def test_successful_render_runs_trafilatura() -> None:
    """A RenderedPage(ok) drives the tier's HTML→markdown pipeline."""
    html = "<html><body><h1>Hello</h1><p>" + ("Body content. " * 80) + "</p></body></html>"
    backend = _StubBackend(
        RenderedPage(
            outcome=RenderOutcome.ok,
            html=html,
            final_url="https://example.com/final",
            status_code=200,
            js_executed=True,
            bytes_transferred=len(html),
        )
    )
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=_make_state(), backend=backend)

    assert result.verdict == Verdict.ok
    assert result.from_browser is True
    assert result.js_executed is True
    assert "Body content" in result.pre_rendered.content_md
    assert result.final_url == "https://example.com/final"


@pytest.mark.asyncio
async def test_timeout_outcome_yields_timeout_verdict() -> None:
    backend = _StubBackend(RenderedPage(outcome=RenderOutcome.timeout, final_url="https://slow.example/", js_executed=True, wall_ms=1000))
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://slow.example/", state=_make_state(), backend=backend)
    assert result.verdict == Verdict.timeout
    assert result.js_executed is True


@pytest.mark.asyncio
async def test_unavailable_outcome_yields_unavailable() -> None:
    backend = _StubBackend(RenderedPage(outcome=RenderOutcome.unavailable, detail="browser launch failed: firefox spawn failed"))
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=_make_state(), backend=backend)
    assert result.verdict == Verdict.connection_error
    assert result.operator_hint.code == "browser_unavailable"
    assert "launch failed" in result.operator_hint.message


@pytest.mark.asyncio
async def test_error_outcome_yields_internal_error_hint() -> None:
    backend = _StubBackend(RenderedPage(outcome=RenderOutcome.error, detail="RuntimeError: net::ERR_NAME_NOT_RESOLVED", js_executed=True))
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=_make_state(), backend=backend)

    assert result.verdict == Verdict.connection_error
    assert result.from_browser is True
    hint = result.operator_hint
    assert hint is not None
    assert hint.code == "browser_internal_error"
    assert hint.message.startswith("RuntimeError")
    assert "ERR_NAME_NOT_RESOLVED" in hint.message
    assert hint.fix is not None


@pytest.mark.asyncio
async def test_no_backend_injected_yields_unavailable() -> None:
    tier = REGISTRY["browser"]
    result = await tier.fetch("https://example.com/", state=_make_state(), backend=None)
    assert result.verdict == Verdict.connection_error
    assert result.operator_hint.code == "browser_unavailable"


@pytest.mark.asyncio
async def test_emit_browser_stderr_logs_typed_event() -> None:
    """The domain sink emits one `BrowserSubprocessStderr` event per line."""
    import logging

    from a2web.state import _emit_browser_stderr

    records: list[logging.LogRecord] = []

    class _Rec(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("a2kit")
    handler = _Rec()
    prior_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        await _emit_browser_stderr("TypeError: boom")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)

    matched = [r for r in records if r.getMessage() == "BrowserSubprocessStderr"]
    assert len(matched) == 1
    assert getattr(matched[0], "a2kit_fields", {}).get("line") == "TypeError: boom"


def test_browser_in_registry_not_in_tier_order() -> None:
    from a2web.tiers import REGISTRY as REAL_REGISTRY
    from a2web.tiers import TIER_ORDER

    assert "browser" in REAL_REGISTRY
    assert "browser" not in TIER_ORDER
