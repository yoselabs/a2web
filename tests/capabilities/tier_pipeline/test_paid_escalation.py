"""Paid last-resort tier: env-gating, out-of-band dispatch, fail-loud auth stop.

Covers task 4.8 of `reddit-reachability-never-silent-miss`:
- un-keyed → the paid tiers never register (zero-config never incurs cost);
- keyed → dispatched only after the free ladder hits a wall, and its content
  installs as the winning tier;
- bad key → `paid_auth_error` STOPs escalation and surfaces loudly (no silent
  fall-through to a sibling paid tier or a cheaper result).
"""

from __future__ import annotations

import pytest

from a2web._manifests.tiers import firecrawl as firecrawl_manifest
from a2web._manifests.tiers import zyte as zyte_manifest
from a2web._plugin import Unavailable
from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult, _load_tier_registry
from tests.conftest import make_default_state

# Cloudflare interstitial — the gate flags this as block_page_detected, driving
# the free ladder to a wall so the paid last resort becomes eligible.
_BLOCK_HTML = (
    b"<html><head><title>Just a moment...</title></head><body><h1>Just a moment...</h1><noscript>cf-chl-bypass</noscript></body></html>"
)


class _BlockedRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_BLOCK_HTML, content_type="text/html", status_code=200, final_url=url)


class _OkPaidTier:
    """A keyed paid service that passes the wall and returns real content."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._md = f"# Recovered by {name}\n\n" + ("Paid content. " * 80)

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=self._md.encode("utf-8"),
            content_type="text/markdown",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=self._md, title=f"Recovered by {self.name}"),
            verdict=Verdict.ok,
        )


class _BadKeyPaidTier:
    """A keyed paid service whose key is rejected — auth/billing failure."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del url, state, kwargs
        return TierResult(body=b"", content_type="text/markdown", status_code=401, final_url="", verdict=Verdict.paid_auth_error)


# --------------------------------------------------------------------- #
# Env-gating (task 4.1 / 4.3)
# --------------------------------------------------------------------- #


def test_paid_manifests_unavailable_without_key() -> None:
    assert isinstance(zyte_manifest.MANIFEST.factory(AppSettings(zyte_key="")), Unavailable)
    assert isinstance(firecrawl_manifest.MANIFEST.factory(AppSettings(firecrawl_key="")), Unavailable)
    # Out-of-band priority so they never enter TIER_ORDER.
    assert zyte_manifest.MANIFEST.priority == -1
    assert firecrawl_manifest.MANIFEST.priority == -1


def test_unkeyed_registry_omits_paid_tiers() -> None:
    assert "zyte" not in REGISTRY
    assert "firecrawl" not in REGISTRY


def test_keyed_registry_registers_paid_tiers_out_of_band(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2WEB_ZYTE_KEY", "zk")
    monkeypatch.setenv("A2WEB_FIRECRAWL_KEY", "fk")
    registry, tier_order = _load_tier_registry()
    assert "zyte" in registry
    assert "firecrawl" in registry
    # Registered but never in the linear tier loop — dispatched out-of-band.
    assert "zyte" not in tier_order
    assert "firecrawl" not in tier_order


# --------------------------------------------------------------------- #
# Dispatch + fail-loud (task 4.5 / 4.6)
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_paid_tier_dispatched_on_wall_and_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A walled free ladder escalates to the paid tier, which wins the fetch."""
    monkeypatch.setitem(REGISTRY, "raw", _BlockedRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _OkPaidTier("zyte"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://walled.example/article", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "zyte"
    assert result.title == "Recovered by zyte"
    assert any(d.step == "zyte" for d in result.diagnostics)
    # A successful retrieval is NOT incomplete.
    assert result.retrieval_incomplete is False


# Thin JS-shell SPA: <500 chars of extractable text, a <script> tag, and a
# root marker (`id="root"`) — the block detector flags this length_floor +
# subsystem=js_required. The autouse browser stub is unavailable, so the browser
# rung exhausts and the paid render becomes the last resort.
_SPA_SHELL_HTML = b'<html><head><title>Search</title></head><body><div id="root"></div><script src="/static/app.js"></script></body></html>'


class _SpaShellRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_SPA_SHELL_HTML, content_type="text/html", status_code=200, final_url=url)


@pytest.mark.asyncio
async def test_js_required_spa_shell_escalates_to_paid_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raw SPA shell that the (unavailable) browser rung can't render escalates
    to the paid render tier, which wins the fetch — search-…-guard P1."""
    monkeypatch.setitem(REGISTRY, "raw", _SpaShellRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _OkPaidTier("zyte"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://spa.example/?q=claude", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "zyte"
    assert any(d.step == "zyte" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_paid_not_dispatched_when_ladder_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean fetch never touches the paid tier (no speculative cost)."""

    class _OkRawTier:
        name = "raw"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            md = "# Fine\n\n" + ("Real readable body content here. " * 80)
            return TierResult(
                body=md.encode("utf-8"),
                content_type="text/html",
                status_code=200,
                final_url=url,
                pre_rendered=Rendered(content_md=md, title="Fine"),
                verdict=Verdict.ok,
            )

    monkeypatch.setitem(REGISTRY, "raw", _OkRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _OkPaidTier("zyte"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://fine.example/", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "raw"
    assert not any(d.step == "zyte" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_bad_paid_key_fails_loud_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad paid key surfaces `paid_auth_error` loudly and STOPS — the sibling
    paid tier (which WOULD succeed) is never tried, and no cheaper result masks it."""
    monkeypatch.setitem(REGISTRY, "raw", _BlockedRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _BadKeyPaidTier("zyte"))
    # firecrawl would succeed — proving STOP means it must NOT run.
    monkeypatch.setitem(REGISTRY, "firecrawl", _OkPaidTier("firecrawl"))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://walled.example/article", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    # The authoritative paid_auth_error wins the verdict — loud, not masked.
    assert any(d.step == "zyte" and d.verdict == Verdict.paid_auth_error for d in result.diagnostics)
    # STOP: the sibling paid tier never ran.
    assert not any(d.step == "firecrawl" for d in result.diagnostics)
    assert result.tier != "firecrawl"
    # never-silently-miss: the miss is explicit.
    assert result.retrieval_incomplete is True
