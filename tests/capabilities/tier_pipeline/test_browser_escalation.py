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
async def test_browser_internal_error_hint_reaches_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """A browser-tier internal error surfaces as a browser_internal_error hint."""
    from a2web.models import OperatorHint

    class _InternalErrorBrowserTier:
        name = "browser"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=0,
                final_url=url,
                from_browser=True,
                js_executed=True,
                operator_hint=OperatorHint(
                    code="browser_internal_error",
                    message="RuntimeError: net::ERR_CONNECTION_RESET",
                    fix="retry",
                ),
                verdict=Verdict.connection_error,
            )

    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _InternalErrorBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://anubis.example/", state=_make_state())

    assert result.status == FetchStatus.failed
    assert any(h.code == "browser_internal_error" for h in result.operator_hints)


class _StillBlockedBrowserTier:
    """A browser rung whose render still trips the gate (re-triggers anubis)."""

    def __init__(self, name: str, counter: dict[str, int]) -> None:
        self.name = name
        self._counter = counter

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        self._counter[self.name] = self._counter.get(self.name, 0) + 1
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


@pytest.mark.asyncio
async def test_fast_rung_thin_escalates_to_robust(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fast browser rung comes back blocked → robust CDP rung recovers it.

    The fast→robust ladder is the existing browser rule firing twice: the
    fast `browser` rung is dispatched first; its still-blocked result keeps the
    gate wanting browser, so the orchestrator dispatches the `browser_robust`
    rung, which clears the gate.
    """
    counter: dict[str, int] = {}
    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _StillBlockedBrowserTier("browser", counter))
    monkeypatch.setitem(REGISTRY, "browser_robust", _RecoveringBrowserTier())  # robust recovers
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://anubis.example/", state=_make_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "browser_robust"  # robust rung produced the winning render
    assert counter["browser"] == 1  # fast rung tried exactly once first
    steps = [d.step for d in result.diagnostics]
    assert "browser" in steps and "browser_robust" in steps  # both rungs in the log


@pytest.mark.asyncio
async def test_browser_dispatch_capped_at_two_rungs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both rungs blocked: fast then robust fire once each, then no third dispatch."""
    counter: dict[str, int] = {}
    monkeypatch.setitem(REGISTRY, "raw", _AnubisRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _StillBlockedBrowserTier("browser", counter))
    monkeypatch.setitem(REGISTRY, "browser_robust", _StillBlockedBrowserTier("browser_robust", counter))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://anubis.example/", state=_make_state())

    assert counter["browser"] == 1  # fast rung: exactly once
    assert counter["browser_robust"] == 1  # robust rung: exactly once
    assert result.status == FetchStatus.failed  # both blocked → no recovery, capped


# --------------------------------------------------------------------- #
# Regate carries the escalation signal (browser-backend-bakeoff).
# This is the shared mechanism behind the fast→robust ladder AND the
# archive→browser path: `_regate_after_escalation` re-evaluates installed
# escalation content and now carries `escalation` so a still-blocked result
# can re-trigger the playbook. Tested path-independently at the unit level;
# the browser path is also covered end-to-end above.
# --------------------------------------------------------------------- #


def _bare_fc() -> object:
    from datetime import UTC, datetime

    from a2web.fetcher import FetchContext

    return FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="x",
        sqlite=None,
        bypass_cache=True,
        url="https://x.com/",
        final_url="https://x.com/",
    )


def test_regate_carries_browser_escalation_on_still_blocked_content() -> None:
    """A re-gated escalation result that still needs JS carries next_tier=browser.

    Before the fix the regate observation dropped `escalation`, so a
    success-but-still-blocked browser/archive render could never re-trigger the
    browser rule — the fast→robust ladder (and archive→browser) couldn't fire.
    """
    from a2web.decision_log import ObservationKind
    from a2web.fetcher import _regate_after_escalation

    fc = _bare_fc()
    fc.content_md = "anubis challenge in progress — verifying your browser"  # block_detector → browser
    _regate_after_escalation(fc)

    last = fc.observations[-1]
    assert last.kind is ObservationKind.gate_outcome
    assert last.source == "regate"
    assert last.verdict is not Verdict.ok
    assert last.escalation is not None
    assert last.escalation.next_tier == "browser"


def test_regate_carries_no_escalation_on_clean_content() -> None:
    """Clean re-gated content carries no escalation — no spurious re-dispatch."""
    from a2web.fetcher import _regate_after_escalation

    fc = _bare_fc()
    fc.content_md = "# Real Article\n\n" + ("Real readable body content. " * 80)
    _regate_after_escalation(fc)

    last = fc.observations[-1]
    assert last.verdict is Verdict.ok
    assert last.escalation is None
