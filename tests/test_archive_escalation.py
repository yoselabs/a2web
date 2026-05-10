"""Orchestrator playbook escalation: paywall → archive → re-gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from purgatory import AsyncCircuitBreakerFactory

from a2web.fetcher import fetch
from a2web.log.writer import LogWriter
from a2web.models import FetchStatus, Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, TierResult

if TYPE_CHECKING:
    pass


_BLOCK_HTML = (
    b"<html><head><title>Just a moment...</title></head>"
    b"<body><h1>Just a moment...</h1><noscript>cf-chl-bypass</noscript></body></html>"
)


class _BlockedTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=_BLOCK_HTML,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


class _RecoveringArchiveTier:
    name = "archive"

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        del state
        markdown = "# Recovered Article\n\n" + ("Real content. " * 80)
        return TierResult(
            body=markdown.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            tier_extras={
                "from_archive": True,
                "source": "wayback",
                "snapshot_age_days": 5,
                "pre_rendered": {
                    "content_md": markdown,
                    "title": "Recovered Article",
                    "byline": None,
                    "headings": [],
                },
            },
            verdict=Verdict.ok,
        )


def _make_state() -> AppState:
    settings = AppSettings()
    return AppState(
        settings=settings,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=True),
    )


@pytest.mark.asyncio
async def test_paywall_escalates_to_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _BlockedTier())
    monkeypatch.setitem(REGISTRY, "archive", _RecoveringArchiveTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://nyt.com/article", state=_make_state())

    assert result.status == FetchStatus.ok
    assert result.tier == "archive"
    assert result.title == "Recovered Article"
    # Archive results don't write to cache
    assert result.cache.value == "miss"


@pytest.mark.asyncio
async def test_archive_failure_keeps_original_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """When archive returns not_found, original block_page verdict stands."""
    # conftest's _NotFoundArchiveTier is already in place

    class _RealBlockedTier:
        name = "raw"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=_BLOCK_HTML, content_type="text/html", status_code=200, final_url=url)

    monkeypatch.setitem(REGISTRY, "raw", _RealBlockedTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://blocked.example/", state=_make_state())

    assert result.status == FetchStatus.failed
    # Block page verdict survives the failed escalation
    assert any(d.verdict == Verdict.block_page_detected for d in result.diagnostics)
