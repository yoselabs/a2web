"""SiteHandlerTier — dispatch to matched handler, fall through on no_match."""

from __future__ import annotations

import pytest

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState, build_state
from a2web.tiers import TierResult
from a2web.tiers.site_handler import SiteHandlerTier


def _state() -> AppState:
    return build_state(settings=AppSettings())


@pytest.mark.asyncio
async def test_no_match_returns_silent_skip() -> None:
    """Generic URL with no matching handler → `no_match=True`."""
    result = await SiteHandlerTier().fetch("https://example.com/", state=_state())

    assert result.no_match is True
    assert result.verdict == Verdict.other
    assert result.body == b""


@pytest.mark.asyncio
async def test_matched_handler_is_delegated_to(monkeypatch: pytest.MonkeyPatch) -> None:
    """A matched handler's TierResult flows out + `handler_name` is filled in."""

    class _FakeHandler:
        name = "fake-handler"

        def matches(self, url: str) -> bool:
            return "matched.example" in url

        async def fetch(self, url: str, *, state: AppState) -> TierResult:
            del state
            return TierResult(
                body=b"<html>handler output</html>",
                content_type="text/html",
                status_code=200,
                final_url=url,
                verdict=Verdict.ok,
            )

    fake = _FakeHandler()

    def fake_match_handler(url: str) -> _FakeHandler | None:
        return fake if fake.matches(url) else None

    monkeypatch.setattr("a2web.tiers.site_handler.match_handler", fake_match_handler)

    result = await SiteHandlerTier().fetch("https://matched.example/post/1", state=_state())

    assert result.verdict == Verdict.ok
    assert result.body == b"<html>handler output</html>"
    assert result.handler_name == "fake-handler"  # Filled in by SiteHandlerTier


@pytest.mark.asyncio
async def test_matched_handler_preserves_its_own_handler_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the handler already set `handler_name`, the tier doesn't overwrite it."""

    class _FakeHandler:
        name = "outer-name"

        async def fetch(self, url: str, *, state: AppState) -> TierResult:
            del state
            return TierResult(
                body=b"x",
                content_type="text/html",
                status_code=200,
                final_url=url,
                verdict=Verdict.ok,
                handler_name="inner-name",
            )

    monkeypatch.setattr("a2web.tiers.site_handler.match_handler", lambda url: _FakeHandler())

    result = await SiteHandlerTier().fetch("https://x/", state=_state())
    assert result.handler_name == "inner-name"
