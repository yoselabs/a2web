"""Correlated-witness detection (fix-zendriver-robust-rung §3).

`browser_robust` is meant to be a DISTINCT evasion engine from the fast `browser`
rung so a second escalation is an independent second witness (load-bearing for
`classify_terminal`'s >=2 agreement + `is_confirmed_empty`). When it resolves to
the SAME engine (the homelab workaround pointing the robust rung at patchright
while zendriver is dead), the render is a same-engine retry, not independence.

This must be OBSERVABLE — the detectable revert trigger for the workaround. When
the robust rung fires with `browser_backend_robust == browser_backend`, the
orchestrator emits a `CorrelatedWitnessRung` WARNING event and stamps
`correlated_witness` on the `browser_robust` diagnostic. A correctly-configured
deployment (distinct engines) emits nothing.
"""

from __future__ import annotations

import logging

import pytest

from a2web.fetcher import fetch
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state

# A JS-SPA shell: <script> + a root marker → gate fingerprints `js_required`, so the
# fetch keeps its full fast→robust budget and the robust rung actually fires.
_SPA_SHELL_HTML = b'<html><body><div id="root"></div><script>window.__app=1</script></body></html>'


def _spa_raw(name: str = "raw") -> object:
    class _T:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=_SPA_SHELL_HTML, content_type="text/html", status_code=200, final_url=url, verdict=Verdict.ok)

    _T.name = name  # type: ignore[attr-defined]
    return _T()


def _thin_browser(name: str) -> object:
    """A browser that under-renders the SPA to a thin body — so the fast rung stays
    thin and the robust rung is dispatched."""

    class _B:
        async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
            del state, backend, scroll, kwargs
            return TierResult(
                body=_SPA_SHELL_HTML,
                content_type="text/html",
                status_code=200,
                final_url=url,
                from_browser=True,
                pre_rendered=Rendered(content_md="Thin under-render."),
                verdict=Verdict.ok,
            )

    _B.name = name  # type: ignore[attr-defined]
    return _B()


def _install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _spa_raw())
    monkeypatch.setitem(REGISTRY, "browser", _thin_browser("browser"))
    monkeypatch.setitem(REGISTRY, "browser_robust", _thin_browser("browser_robust"))


@pytest.mark.asyncio
async def test_same_engine_robust_rung_emits_signal(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """robust engine == fast engine → the robust diagnostic is stamped
    `correlated_witness` and a CorrelatedWitnessRung WARNING is logged."""
    _install(monkeypatch)
    state = make_default_state(settings=AppSettings(browser_backend="patchright", browser_backend_robust="patchright"))

    with caplog.at_level(logging.WARNING, logger="a2kit"):
        fr = await fetch("https://spa.example/app", state=state, debug=True)

    robust_diags = [d for d in fr.diagnostics if d.step == "browser_robust"]
    assert robust_diags, "the robust rung must have fired (js_required keeps the 2-render budget)"
    assert any(d.extra.get("correlated_witness") == "patchright" for d in robust_diags)
    assert any(r.getMessage() == "CorrelatedWitnessRung" for r in caplog.records)


@pytest.mark.asyncio
async def test_distinct_engines_emit_no_signal(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """robust engine != fast engine (the intended config) → no correlated-witness
    signal, on either the diagnostic or the log."""
    _install(monkeypatch)
    state = make_default_state(settings=AppSettings(browser_backend="patchright", browser_backend_robust="zendriver"))

    with caplog.at_level(logging.WARNING, logger="a2kit"):
        fr = await fetch("https://spa.example/app", state=state, debug=True)

    assert not any("correlated_witness" in d.extra for d in fr.diagnostics)
    assert not any(r.getMessage() == "CorrelatedWitnessRung" for r in caplog.records)
