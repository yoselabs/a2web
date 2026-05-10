"""Archive tier tests — Wayback hit, archive.ph hit, both miss, hedge cancel."""

from __future__ import annotations

import httpx
import pytest

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers.archive import ArchiveTier


def _state() -> AppState:
    return AppState(settings=AppSettings())


@pytest.fixture(autouse=True)
def _disable_archive_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override conftest's archive stub for this module — we test the real tier."""
    from a2web.tiers import REGISTRY
    from a2web.tiers.archive import ArchiveTier as _Real

    monkeypatch.setitem(REGISTRY, "archive", _Real())


@pytest.mark.asyncio
async def test_wayback_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wayback CDX returns a row → snapshot fetched + extracted."""
    cdx_calls = {"n": 0}

    def httpx_handler(request: httpx.Request) -> httpx.Response:
        cdx_calls["n"] += 1
        if "cdx/search" in request.url.path:
            return httpx.Response(200, json=[["timestamp", "original"], ["20240101000000", "https://x.com/"]])
        if "/web/" in request.url.path:
            html = "<html><body><article><h1>Snap</h1><p>" + ("body " * 200) + "</p></article></body></html>"
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    transport = httpx.MockTransport(httpx_handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    # Force archive.ph to lose by making it return None
    async def fake_archive_ph(url: str) -> str | None:
        del url
        return None

    monkeypatch.setattr("a2web.tiers.archive._archive_ph_lookup", fake_archive_ph)

    result = await ArchiveTier().fetch("https://x.com/", state=_state())

    assert result.verdict == Verdict.ok
    assert result.tier_extras["from_archive"] is True
    assert result.tier_extras["source"] == "wayback"
    assert "snapshot_age_days" in result.tier_extras
    assert "Snap" in result.tier_extras["pre_rendered"]["content_md"]


@pytest.mark.asyncio
async def test_archive_ph_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """archive.ph wins over an empty Wayback."""
    def httpx_handler(request: httpx.Request) -> httpx.Response:
        if "cdx/search" in request.url.path:
            return httpx.Response(200, json=[["timestamp", "original"]])  # no rows
        return httpx.Response(404)

    transport = httpx.MockTransport(httpx_handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    async def fake_archive_ph(url: str) -> str | None:
        del url
        return "<html><body><article><h1>Mirror</h1><p>" + ("text " * 200) + "</p></article></body></html>"

    monkeypatch.setattr("a2web.tiers.archive._archive_ph_lookup", fake_archive_ph)

    result = await ArchiveTier().fetch("https://x.com/", state=_state())

    assert result.verdict == Verdict.ok
    assert result.tier_extras["source"] == "archive.ph"
    assert "Mirror" in result.tier_extras["pre_rendered"]["content_md"]


@pytest.mark.asyncio
async def test_both_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    def httpx_handler(request: httpx.Request) -> httpx.Response:
        if "cdx/search" in request.url.path:
            return httpx.Response(200, json=[["timestamp", "original"]])
        return httpx.Response(404)

    transport = httpx.MockTransport(httpx_handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    async def fake_archive_ph(url: str) -> str | None:
        del url
        return None

    monkeypatch.setattr("a2web.tiers.archive._archive_ph_lookup", fake_archive_ph)

    result = await ArchiveTier().fetch("https://x.com/", state=_state())

    assert result.verdict == Verdict.not_found
    assert result.tier_extras["from_archive"] is True
    assert "pre_rendered" not in result.tier_extras


def test_strip_wayback_chrome_removes_div() -> None:
    from a2web.tiers.archive import _strip_wayback_chrome

    html = '<html><body><div id="wm-ipp-base"><a>chrome</a></div><p>real</p></body></html>'
    cleaned = _strip_wayback_chrome(html)
    assert "wm-ipp-base" not in cleaned
    assert "real" in cleaned


def test_snapshot_age_days_parses_timestamp() -> None:
    from a2web.tiers.archive import _snapshot_age_days

    age = _snapshot_age_days("20240101000000")
    assert isinstance(age, int)
    assert age >= 0


def test_snapshot_age_days_invalid() -> None:
    from a2web.tiers.archive import _snapshot_age_days

    assert _snapshot_age_days("not-a-timestamp") is None
