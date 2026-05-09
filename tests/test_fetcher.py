"""Fetcher integration tests — using a mock Tier feeding canned HTML."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from purgatory import AsyncCircuitBreakerFactory

from a2web.cache.sqlite_cache import cache_dir
from a2web.fetcher import fetch
from a2web.log.writer import LogWriter
from a2web.models import CacheState, FetchStatus, Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, TierResult

_FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A2WEB_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("A2WEB_LOG_DIR", str(tmp_path / "logs"))


class _MockTier:
    """In-memory tier that returns a fixed body and headers."""

    name: str = "mock"

    def __init__(self, body: bytes, *, content_type: str = "text/html") -> None:
        self._body = body
        self._content_type = content_type

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        return TierResult(
            body=self._body,
            content_type=self._content_type,
            status_code=200,
            final_url=url,
            headers={"etag": '"v1"'},
        )


def _make_state(*, settings: AppSettings | None = None) -> AppState:
    resolved = settings or AppSettings()
    return AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
    )


def _swap_tier(monkeypatch: pytest.MonkeyPatch, tier: object) -> None:
    """Replace the raw tier in the registry for a single test."""
    monkeypatch.setitem(REGISTRY, "raw", tier)
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)


@pytest.mark.asyncio
async def test_blog_fixture_yields_real_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "blog.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    state = _make_state()
    result = await fetch("https://example.org/post", state=state)

    assert result.status == FetchStatus.ok
    assert result.tier == "mock"
    assert result.cache == CacheState.miss
    assert result.title is not None
    assert "adaptive" in result.title.lower()
    assert len(result.content_md) > 500
    assert result.meta.get("og.type") == "article"
    assert any(h.text.startswith("Why one fetch") for h in result.headings)


@pytest.mark.asyncio
async def test_block_page_fails_and_does_not_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    state = _make_state()
    result = await fetch("https://blocked.example/page", state=state)

    assert result.status == FetchStatus.failed
    verdicts = [d.verdict for d in result.diagnostics]
    assert Verdict.block_page_detected in verdicts

    # No row landed in the cache
    db_path = cache_dir() / "cache.sqlite"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
    assert row[0] == 0


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "blog.html").read_bytes()

    # First call: real "fetch" via mock; should write cache
    first_tier = _MockTier(body)
    _swap_tier(monkeypatch, first_tier)
    state = _make_state()
    first = await fetch("https://example.org/post", state=state)
    assert first.cache == CacheState.miss
    assert first.status == FetchStatus.ok

    # Second call: tier returns 304 to confirm conditional GET → cached body
    class _NotModifiedTier:
        name = "raw"

        async def fetch(self, url: str, *, state: AppState, conditional_extras=None):
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=304,
                final_url=url,
                headers={"etag": '"v1"'},
                tier_extras={"conditional_hit": True},
            )

    _swap_tier(monkeypatch, _NotModifiedTier())
    second = await fetch("https://example.org/post", state=state)
    assert second.cache == CacheState.hit
    assert second.status == FetchStatus.ok
    assert second.title is not None
    assert second.content_md == first.content_md


@pytest.mark.asyncio
async def test_live_only_host_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "blog.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    settings = AppSettings(live_only_hosts=["live.example"])
    state = _make_state(settings=settings)
    result = await fetch("https://live.example/article", state=state)

    assert result.cache == CacheState.bypass
    db_path = cache_dir() / "cache.sqlite"
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        assert count == 0


@pytest.mark.asyncio
async def test_successful_fetch_appends_log_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = (_FIX / "blog.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    state = _make_state()
    await fetch("https://example.org/post", state=state)
    await state.log_writer.aclose()  # type: ignore[union-attr]

    log_files = list((tmp_path / "logs").glob("fetches-*.ndjson"))
    assert len(log_files) == 1
    import json

    lines = [line for line in log_files[0].read_text().splitlines() if line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["status"] == "ok"
    assert record["tier"] == "mock"
    assert record["url"] == "https://example.org/post"


@pytest.mark.asyncio
async def test_failed_fetch_also_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    state = _make_state()
    await fetch("https://blocked.example/page", state=state)
    await state.log_writer.aclose()  # type: ignore[union-attr]

    log_files = list((tmp_path / "logs").glob("fetches-*.ndjson"))
    assert len(log_files) == 1
    import json

    record = json.loads(log_files[0].read_text().splitlines()[0])
    assert record["status"] == "failed"
    assert record["verdict"] == "block_page_detected"


@pytest.mark.asyncio
async def test_disabled_log_writer_creates_no_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = (_FIX / "blog.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    state = _make_state(settings=AppSettings(log_enabled=False))
    await fetch("https://example.org/post", state=state)

    log_root = tmp_path / "logs"
    if log_root.exists():
        assert list(log_root.glob("fetches-*.ndjson")) == []


@pytest.mark.asyncio
async def test_log_write_failure_appends_operator_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = (_FIX / "blog.html").read_bytes()
    _swap_tier(monkeypatch, _MockTier(body))

    class _BrokenWriter:
        async def write_record(self, _record: object) -> None:
            raise OSError("disk on fire")

    state = _make_state()
    state.log_writer = _BrokenWriter()  # type: ignore[assignment]

    response = await fetch("https://example.org/post", state=state)
    codes = [hint.code for hint in response.operator_hints]
    assert "log_write_failed" in codes


@pytest.mark.asyncio
async def test_pre_rendered_handler_skips_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-rendered tier_extras bypasses trafilatura/htmldate/metadata."""
    from a2web.models import Heading

    class _PreRenderedHandler:
        name = "site_handler:reddit"

        async def fetch(self, url: str, *, state: AppState) -> TierResult:
            return TierResult(
                body=b'{"foo":"bar"}',
                content_type="application/json",
                status_code=200,
                final_url=url,
                tier_extras={
                    "handler_name": "site_handler:reddit",
                    "pre_rendered": {
                        "content_md": "# Pre-rendered\n\n" + ("Body line. " * 100),
                        "title": "Pre-rendered",
                        "byline": "u/somebody",
                        "headings": [Heading(level=1, text="Pre-rendered")],
                    },
                },
            )

    monkeypatch.setitem(REGISTRY, "site_handler", _PreRenderedHandler())
    state = _make_state()
    result = await fetch("https://www.reddit.com/r/x/comments/abc/", state=state)

    assert result.status == FetchStatus.ok
    assert result.tier == "site_handler:reddit"
    assert result.title == "Pre-rendered"
    assert result.content_md.startswith("# Pre-rendered")
    # No extract diagnostic row when handler pre-renders
    steps = [d.step for d in result.diagnostics]
    assert "extract" not in steps


@pytest.mark.asyncio
async def test_no_match_handler_emits_no_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    """SiteHandlerTier returning no_match must not produce a diagnostic row."""
    body = (_FIX / "blog.html").read_bytes()
    # Keep the real SiteHandlerTier; example.org won't match any handler.
    # Replace `raw` with a mock so we have a deterministic body.
    monkeypatch.setitem(REGISTRY, "raw", _MockTier(body))

    state = _make_state()
    result = await fetch("https://example.org/post", state=state)

    steps = [d.step for d in result.diagnostics]
    assert "site_handler" not in steps
    assert "raw" in steps[0]  # first row is the raw tier
