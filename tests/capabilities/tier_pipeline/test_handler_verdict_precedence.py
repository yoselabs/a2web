"""Orchestrator verdict precedence: a site handler's `not_found` survives the cascade.

A site handler returning `Verdict.not_found` is the strongest negative signal
in the pipeline. When the fetch ultimately fails, that verdict must outrank a
vaguer downstream verdict (`length_floor`) — but it must never clobber a
genuine recovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, TierResult
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

# A 200 OK page whose body extracts to well under the 500-char length floor and
# carries no block markers / script tags — the gate verdict is plain length_floor.
# A thin-but-present page (real visible text, still under LENGTH_FLOOR) — a
# length_floor failure, NOT a near-empty blank_page shell. Kept above the
# blank-page visible-text threshold so this precedence test stays about the
# not_found-vs-length_floor rule, not blank detection.
_THIN_HTML = (
    b"<html><head><title>Archived</title></head><body><p>This entry is thin: a short "
    b"archived stub with a little real text but well under the length floor.</p></body></html>"
)


class _NotFoundHandlerTier:
    """Stub site handler: confirms the content is gone."""

    name: str = "site_handler"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=b"",
            content_type="text/html",
            status_code=404,
            final_url=url,
            handler_name="reddit",
            verdict=Verdict.not_found,
        )


class _ThinRawTier:
    """Stub raw tier: 200 OK + a sub-length-floor body (deleted-content SPA shell)."""

    name: str = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=_THIN_HTML,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


class _RichRawTier:
    """Stub raw tier: 200 OK + real, gate-passing article HTML."""

    name: str = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=self._body,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


@pytest.fixture(autouse=True)
def _isolate_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A2WEB_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("A2WEB_LOG_DIR", str(tmp_path / "logs"))


@pytest.mark.asyncio
async def test_handler_not_found_survives_downstream_length_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deleted page — the handler's `not_found` outranks the raw tier's `length_floor`."""
    monkeypatch.setitem(REGISTRY, "site_handler", _NotFoundHandlerTier())
    monkeypatch.setitem(REGISTRY, "raw", _ThinRawTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    # debug=True — `diagnostics` is debug-only on the wire; the attribute is
    # always populated, but keeping the run in debug mode mirrors real probes.
    result = await fetch("https://reddit.com/r/programming/comments/deleted/", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert "verdict=not_found" in result.diagnostics_summary
    assert "verdict=length_floor" not in result.diagnostics_summary


@pytest.mark.asyncio
async def test_downstream_recovery_wins_over_handler_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine raw-tier recovery stands — the precedence rule fires only on failure."""
    body = (FIXTURES_DIR / "blog.html").read_bytes()
    monkeypatch.setitem(REGISTRY, "site_handler", _NotFoundHandlerTier())
    monkeypatch.setitem(REGISTRY, "raw", _RichRawTier(body))
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://reddit.com/r/programming/comments/live/", state=make_default_state())

    assert result.status == FetchStatus.ok
    assert len(result.content_md) > 500


@pytest.mark.asyncio
async def test_no_handler_not_found_leaves_length_floor_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no handler `not_found` in the fetch, a `length_floor` failure stands as-is."""
    monkeypatch.setitem(REGISTRY, "raw", _ThinRawTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    # No site_handler stub — the real SiteHandlerTier returns no_match for this
    # generic host and is silently skipped, so `handler_not_found` stays False.
    result = await fetch("https://example.com/some/page", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert "verdict=length_floor" in result.diagnostics_summary
    assert "verdict=not_found" not in result.diagnostics_summary
