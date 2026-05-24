"""Archive tier tests — Wayback hit, archive.ph hit, both miss, branch coverage.

All HTTP now goes through the shared `http_fetch.fetch_bytes` primitive;
tests monkeypatch it directly with a per-URL router that returns
`FetchOutcome` values.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from a2web.models import Verdict
from a2web.packages.http_fetch import FetchOutcome, FetchVerdict
from a2web.state import AppState
from a2web.tiers.archive import ArchiveTier
from tests.conftest import make_default_state


def _state() -> AppState:
    return make_default_state()


def _ok(body: bytes, *, status: int = 200, content_type: str = "text/html") -> FetchOutcome:
    return FetchOutcome(
        body=body,
        content_type=content_type,
        status_code=status,
        final_url="",
        headers={},
        verdict=FetchVerdict.ok,
    )


def _fail(verdict: FetchVerdict = FetchVerdict.connection_error, status: int = 0) -> FetchOutcome:
    return FetchOutcome(body=b"", content_type="", status_code=status, final_url="", headers={}, verdict=verdict)


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, router: Callable[[str], FetchOutcome]) -> None:
    async def _fake(url: str, **kwargs: Any) -> FetchOutcome:
        del kwargs
        return router(url)

    monkeypatch.setattr("a2web.tiers.archive.fetch_bytes", _fake)


@pytest.fixture(autouse=True)
def _disable_archive_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override conftest's archive stub for this module — we test the real tier."""
    from a2web.tiers import REGISTRY
    from a2web.tiers.archive import ArchiveTier as _Real

    monkeypatch.setitem(REGISTRY, "archive", _Real())


@pytest.mark.asyncio
async def test_wayback_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wayback CDX returns a row → snapshot fetched + extracted."""

    snap_html = "<html><body><article><h1>Snap</h1><p>" + ("body " * 200) + "</p></article></body></html>"

    def route(url: str) -> FetchOutcome:
        if "cdx/search" in url:
            return _ok(
                b'[["timestamp", "original"], ["20240101000000", "https://x.com/"]]',
                content_type="application/json",
            )
        if "/web/" in url:
            return _ok(snap_html.encode("utf-8"))
        return _fail(FetchVerdict.not_found, status=404)

    _patch_fetch(monkeypatch, route)

    # Force archive.ph to lose by making it return None.
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

    def route(url: str) -> FetchOutcome:
        if "cdx/search" in url:
            return _ok(b'[["timestamp", "original"]]', content_type="application/json")  # header only
        return _fail(FetchVerdict.not_found, status=404)

    _patch_fetch(monkeypatch, route)

    mirror_html = "<html><body><article><h1>Mirror</h1><p>" + ("text " * 200) + "</p></article></body></html>"

    async def fake_archive_ph(url: str) -> str | None:
        del url
        return mirror_html

    monkeypatch.setattr("a2web.tiers.archive._archive_ph_lookup", fake_archive_ph)

    result = await ArchiveTier().fetch("https://x.com/", state=_state())

    assert result.verdict == Verdict.ok
    assert result.archive_source == "archive.ph"
    assert "Mirror" in result.pre_rendered.content_md


@pytest.mark.asyncio
async def test_both_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    def route(url: str) -> FetchOutcome:
        if "cdx/search" in url:
            return _ok(b'[["timestamp", "original"]]', content_type="application/json")
        return _fail(FetchVerdict.not_found, status=404)

    _patch_fetch(monkeypatch, route)

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
# _wayback_lookup error branches
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wayback_cdx_transport_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    _patch_fetch(monkeypatch, lambda url: _fail(FetchVerdict.connection_error))
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    # An "ok" verdict with a 5xx body still has status_code 503 — but fetch_bytes
    # never returns status_code >= 400 with verdict.ok; a non-200 maps to
    # connection_error. Verify the lookup tolerates both code paths.
    _patch_fetch(monkeypatch, lambda url: _fail(FetchVerdict.connection_error, status=503))
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    _patch_fetch(monkeypatch, lambda url: _ok(b"not json at all", content_type="text/plain"))
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_cdx_header_only_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _wayback_lookup

    _patch_fetch(
        monkeypatch,
        lambda url: _ok(b'[["timestamp", "original"]]', content_type="application/json"),
    )
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_snapshot_transport_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """CDX succeeds, snapshot fetch fails."""
    from a2web.tiers.archive import _wayback_lookup

    def route(url: str) -> FetchOutcome:
        if "cdx" in url:
            return _ok(
                b'[["timestamp", "original"], ["20240101000000", "https://example.com/x"]]',
                content_type="application/json",
            )
        return _fail(FetchVerdict.connection_error)

    _patch_fetch(monkeypatch, route)
    assert await _wayback_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_wayback_snapshot_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """CDX succeeds, snapshot returns not-found."""
    from a2web.tiers.archive import _wayback_lookup

    def route(url: str) -> FetchOutcome:
        if "cdx" in url:
            return _ok(
                b'[["timestamp", "original"], ["20240101000000", "https://example.com/x"]]',
                content_type="application/json",
            )
        return _fail(FetchVerdict.not_found, status=404)

    _patch_fetch(monkeypatch, route)
    assert await _wayback_lookup("https://example.com/x") is None


# --------------------------------------------------------------------- #
# _archive_ph_lookup
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_archive_ph_lookup_transport_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_lookup

    _patch_fetch(monkeypatch, lambda url: _fail(FetchVerdict.connection_error))
    assert await _archive_ph_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_archive_ph_lookup_non_200_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_lookup

    _patch_fetch(monkeypatch, lambda url: _fail(FetchVerdict.not_found, status=404))
    assert await _archive_ph_lookup("https://example.com/x") is None


@pytest.mark.asyncio
async def test_archive_ph_lookup_200_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.tiers.archive import _archive_ph_lookup

    _patch_fetch(monkeypatch, lambda url: _ok(b"<html>archived</html>"))
    assert await _archive_ph_lookup("https://example.com/x") == "<html>archived</html>"
