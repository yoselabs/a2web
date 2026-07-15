"""End-to-end: HTTP-404 terminal semantics (corroboration-keyed not-found).

A dead URL must be reported as gone — honestly, and never dressed as an anti-bot
wall (the incehesap incident). A corroborated 404 is a confident fact (info, not
incomplete); a single uncorroborated 404 keeps the soft-404 caveat (warning,
incomplete). Neither fires the critical `try_user_browser` klaxon.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests.conftest import make_default_state


def _status_tier(name: str, *, verdict: Verdict, status_code: int) -> object:
    class _T:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(body=b"", content_type="text/html", status_code=status_code, final_url=url, verdict=verdict)

    _T.name = name  # type: ignore[attr-defined]
    return _T()


@pytest.mark.asyncio
async def test_corroborated_404_is_gone_confirmed_not_walled(monkeypatch: pytest.MonkeyPatch) -> None:
    """raw:404 + jina:404 (both independent) → gone_confirmed: honest not-found,
    INFO hint, NOT retrieval_incomplete, and NO anti-bot `try_user_browser`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _status_tier("raw", verdict=Verdict.not_found, status_code=404))
    monkeypatch.setitem(REGISTRY, "jina", _status_tier("jina", verdict=Verdict.not_found, status_code=404))

    result = await fetch("https://shop.example/arama?q=deepcool", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    hints = {h.code: h for h in result.operator_hints}
    assert "content_not_found" in hints
    assert hints["content_not_found"].severity == "info"
    assert result.retrieval_incomplete is False  # a verified dead URL is not "incomplete"


@pytest.mark.asyncio
async def test_uncorroborated_404_is_gone_unverified_with_caveat(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single 404 (jina returns a different failure) → gone_unverified: WARNING
    with the soft-404 caveat, retrieval_incomplete, still NO `try_user_browser`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _status_tier("raw", verdict=Verdict.not_found, status_code=404))
    monkeypatch.setitem(REGISTRY, "jina", _status_tier("jina", verdict=Verdict.rate_limited, status_code=429))

    result = await fetch("https://shop.example/arama?q=deepcool", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    hints = {h.code: h for h in result.operator_hints}
    assert "content_not_found" in hints
    assert hints["content_not_found"].severity == "warning"
    assert result.retrieval_incomplete is True


@pytest.mark.asyncio
async def test_authoritative_not_found_stays_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A handler-authoritative gone is definitive → gone_confirmed, and stays
    SILENT (no content_not_found hint, not incomplete) as before."""

    class _AuthoritativeGoneHandler:
        name = "site_handler"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            # The orchestrator marks a site_handler not_found as authoritative.
            return TierResult(
                body=b"",
                content_type="",
                status_code=404,
                final_url=url,
                handler_name="site_handler:reddit",
                verdict=Verdict.not_found,
            )

    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("site_handler",))
    monkeypatch.setitem(REGISTRY, "site_handler", _AuthoritativeGoneHandler())

    result = await fetch("https://www.reddit.com/r/x/comments/deleted/", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    assert not any(h.code == "content_not_found" for h in result.operator_hints)
    assert result.retrieval_incomplete is False
