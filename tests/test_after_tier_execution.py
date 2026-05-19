"""Orchestrator after-tier action execution: RewriteUrl + RetryViaArchive."""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state


def _make_state() -> AppState:
    return make_default_state()


class _CountingRawTier:
    """Captures the URLs raw was called with — for rewrite verification."""

    name = "raw"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        self.calls.append(url)
        # Healthy 200 with article content (passes gate).
        body = ("<html><body><p>" + ("Article body. " * 80) + "</p></body></html>").encode()
        return TierResult(
            body=body,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


@pytest.mark.asyncio
async def test_arxiv_pdf_rewritten_to_abs(monkeypatch: pytest.MonkeyPatch) -> None:
    """next_action_after_tier returns RewriteUrl for arxiv pdf URLs.

    After PR8, the abs URL matches `ArxivHandler` (site_handler tier),
    so we stub that handler to keep this test focused on rewrite logic.
    """
    raw = _CountingRawTier()
    monkeypatch.setitem(REGISTRY, "raw", raw)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    # Disable arxiv handler so the rewritten /abs/ URL falls through to raw.
    from a2web.handlers import _HANDLERS, ArxivHandler

    filtered = tuple(h for h in _HANDLERS if not isinstance(h, ArxivHandler))
    monkeypatch.setattr("a2web.handlers._HANDLERS", filtered)

    result = await fetch("https://arxiv.org/pdf/2401.12345", state=_make_state())

    assert result.status == FetchStatus.ok
    assert raw.calls[0].endswith("/pdf/2401.12345")
    assert any("/abs/2401.12345" in c for c in raw.calls)
    assert "/abs/2401.12345" in result.url


@pytest.mark.asyncio
async def test_rewrite_capped_at_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second RewriteUrl in the same fetch is ignored (anti-loop)."""

    raw = _CountingRawTier()
    monkeypatch.setitem(REGISTRY, "raw", raw)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)
    from a2web.handlers import _HANDLERS, ArxivHandler

    filtered = tuple(h for h in _HANDLERS if not isinstance(h, ArxivHandler))
    monkeypatch.setattr("a2web.handlers._HANDLERS", filtered)

    result = await fetch("https://arxiv.org/pdf/2401.99999", state=_make_state())
    assert result.status == FetchStatus.ok
    assert len(raw.calls) == 2  # original pdf + rewrite to abs


class _CloudflareBlockedRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=b"<html><body>blocked</body></html>",
            content_type="text/html",
            status_code=403,
            final_url=url,
            headers={"server": "cloudflare", "cf-ray": "abc123"},
            verdict=Verdict.connection_error,
        )


class _RecoveringArchiveTier:
    name = "archive"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state
        markdown = "# Recovered\n\n" + ("Real content. " * 80)
        return TierResult(
            body=markdown.encode(),
            content_type="text/html",
            status_code=200,
            final_url=url,
            from_archive=True,
            archive_source="wayback",
            pre_rendered=Rendered(content_md=markdown, title="Recovered"),
            verdict=Verdict.ok,
        )


@pytest.mark.asyncio
async def test_after_tier_cloudflare_403_dispatches_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _CloudflareBlockedRawTier())
    monkeypatch.setitem(REGISTRY, "archive", _RecoveringArchiveTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://blocked.example/", state=_make_state())

    assert result.status == FetchStatus.ok
    assert result.tier == "archive"
    assert result.title == "Recovered"
