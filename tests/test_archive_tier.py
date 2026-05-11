"""Archive tier tests — Wayback hit, archive.ph hit, both miss, hedge cancel."""

from __future__ import annotations

import httpx
import pytest

from a2web.models import Verdict
from a2web.state import AppState, build_state
from a2web.tiers.archive import ArchiveTier


def _state() -> AppState:
    return build_state()


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
    assert result.from_archive is True
    assert result.archive_source == "wayback"
    assert result.snapshot_age_days is not None
    assert "Snap" in result.pre_rendered.content_md


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
    assert result.archive_source == "archive.ph"
    assert "Mirror" in result.pre_rendered.content_md


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
    assert result.from_archive is True
    assert result.pre_rendered is None


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


# --------------------------------------------------------------------- #
# _wayback_lookup error branches (lines 68-69, 71, 74-75, 82-83, 85)
# --------------------------------------------------------------------- #


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))


@pytest.mark.asyncio
async def test_wayback_cdx_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS failure")

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="this is not json")

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_header_only_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """CDX returns header row only when no snapshots exist for the URL."""
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        # Just the header row, no data rows.
        return httpx.Response(200, json=[["timestamp", "original"]])

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_snapshot_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """CDX succeeds, snapshot fetch raises."""
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdx" in str(request.url):
            return httpx.Response(200, json=[["timestamp", "original"], ["20240101000000", "https://example.com/x"]])
        raise httpx.ConnectError("snapshot host down")

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_snapshot_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """CDX succeeds, snapshot returns 404."""
    from a2web.tiers.archive import _wayback_lookup

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdx" in str(request.url):
            return httpx.Response(200, json=[["timestamp", "original"], ["20240101000000", "https://example.com/x"]])
        return httpx.Response(404, text="not found")

    _patch_httpx(monkeypatch, handler)
    assert await _wayback_lookup("https://example.com/x") is None


# --------------------------------------------------------------------- #
# _archive_ph_sync (lines 91-102) + _archive_ph_lookup (line 106)
# --------------------------------------------------------------------- #


class _FakeArchiveResp:
    def __init__(self, *, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_archive_ph_sync_request_exception_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from curl_cffi.requests import exceptions as curl_exceptions

    from a2web.tiers.archive import _archive_ph_sync

    def boom(*args: object, **kwargs: object) -> object:
        raise curl_exceptions.RequestException("connection refused")

    monkeypatch.setattr("a2web.tiers.archive.curl_requests.get", boom)
    assert _archive_ph_sync("https://example.com/x") is None


def test_archive_ph_sync_oserror_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError is the other branch of the except clause."""
    from a2web.tiers.archive import _archive_ph_sync

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("network unreachable")

    monkeypatch.setattr("a2web.tiers.archive.curl_requests.get", boom)
    assert _archive_ph_sync("https://example.com/x") is None


def test_archive_ph_sync_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_sync

    monkeypatch.setattr(
        "a2web.tiers.archive.curl_requests.get",
        lambda *a, **kw: _FakeArchiveResp(status_code=503, text="down"),
    )
    assert _archive_ph_sync("https://example.com/x") is None


def test_archive_ph_sync_200_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_sync

    monkeypatch.setattr(
        "a2web.tiers.archive.curl_requests.get",
        lambda *a, **kw: _FakeArchiveResp(status_code=200, text="<html>archived</html>"),
    )
    assert _archive_ph_sync("https://example.com/x") == "<html>archived</html>"


@pytest.mark.asyncio
async def test_archive_ph_lookup_wraps_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_lookup

    monkeypatch.setattr(
        "a2web.tiers.archive.curl_requests.get",
        lambda *a, **kw: _FakeArchiveResp(status_code=200, text="<html>x</html>"),
    )
    assert await _archive_ph_lookup("https://example.com/x") == "<html>x</html>"
