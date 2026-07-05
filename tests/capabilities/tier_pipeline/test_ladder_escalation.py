"""Escalate to a paid site render — search-retrieval-and-confabulation-guard P4.

A handler sets `escalate_to_render` when its rewritten fetch fails (HN's Algolia
API) or its surface is walled (Reddit search 403). The orchestrator STOPS the
free ladder (raw/jina get fooled by SPA shells / block pages) and renders the
ORIGINAL url directly via the paid tier (Zyte browserHtml). If no paid tier is
keyed, the empty body falls through to the never-silently-miss guarantee.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state


class _EscalatingSiteTier:
    """A site_handler asking for a direct paid render (its converted fetch failed)."""

    name = "site_handler"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=b"",
            content_type="",
            status_code=404,  # even a 404 (normally authoritative) must not end the run
            final_url=url,
            handler_name="site_handler:hn",
            verdict=Verdict.not_found,
            escalate_to_render=True,
        )


class _ShellRawTier:
    """A raw tier that returns a passing-but-useless shell — proves it is NOT used."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Shell\n\n" + ("nav footer chrome " * 60)  # >500 chars: would pass the gate
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Shell"),
            verdict=Verdict.ok,
        )


class _OkPaidTier:
    name = "zyte"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Rendered by Zyte\n\n" + ("Real rendered result content. " * 80)
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Rendered by Zyte"),
            verdict=Verdict.ok,
        )


@pytest.mark.asyncio
async def test_escalate_to_render_dispatches_paid_and_skips_free_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _OkPaidTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://hn.algolia.com/?q=claude", state=make_default_state(), debug=True)

    # Paid render won on the original URL...
    assert result.status == FetchStatus.ok
    assert result.tier == "zyte"
    assert result.title == "Rendered by Zyte"
    # ...and the free ladder was stopped — the shell-returning raw tier never ran.
    assert not any(d.step == "raw" for d in result.diagnostics)
    # The failed handler attempt is still recorded.
    assert any(d.step == "site_handler" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_escalate_to_render_without_paid_key_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """No paid tier keyed → the render can't happen → never-silently-miss."""
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://hn.algolia.com/?q=claude", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert not any(d.step == "raw" for d in result.diagnostics)  # free ladder still skipped
