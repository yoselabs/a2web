"""Shared test fixtures.

Auto-stubs the archive tier so existing tests that trigger paywall /
block_page gate verdicts don't accidentally hit the live network when
the playbook escalation runs. Tests that exercise archive recovery
explicitly opt in by re-monkeypatching `REGISTRY["archive"]`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from a2web.models import OperatorHint, Verdict
from a2web.tiers import REGISTRY, TierResult

if TYPE_CHECKING:
    from a2web.state import AppState


class _NotFoundArchiveTier:
    """Default archive stub: always reports not_found, no network."""

    name: str = "archive"

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        del state
        return TierResult(
            body=b"",
            content_type="text/html",
            status_code=404,
            final_url=url,
            from_archive=True,
            verdict=Verdict.not_found,
        )


class _UnavailableBrowserTier:
    """Default browser stub: never launch Camoufox in unit tests."""

    name: str = "browser"

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        del state
        return TierResult(
            body=b"",
            content_type="text/html",
            status_code=0,
            final_url=url,
            from_browser=True,
            operator_hint=OperatorHint(code="browser_unavailable", message="test stub", fix="n/a"),
            verdict=Verdict.connection_error,
        )


@pytest.fixture(autouse=True)
def _stub_archive_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "archive", _NotFoundArchiveTier())
    monkeypatch.setitem(REGISTRY, "browser", _UnavailableBrowserTier())
