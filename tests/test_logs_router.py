"""LogsRouter — replay/tail/grep tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from a2web.routers import LogsRouter


def _make_record(*, ts: str, url: str, verdict: str = "ok", title: str | None = None) -> dict:
    return {
        "ts": ts,
        "url": url,
        "final_url": url,
        "host": "example.com",
        "tier": "raw",
        "status": "ok" if verdict == "ok" else "failed",
        "verdict": verdict,
        "cache": "miss",
        "total_ms": 100,
        "content_chars": 500,
        "title": title,
        "error": None,
        "diagnostics": [],
    }


def _seed_log(tmp_path: Path, records: list[dict]) -> None:
    log_file = tmp_path / "fetches-2026-05-10.ndjson"
    with log_file.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture
def _logs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("A2WEB_LOG_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_replay_returns_last_record(_logs_dir: Path) -> None:
    _seed_log(
        _logs_dir,
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://x/", title="old"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://x/", title="latest"),
        ],
    )
    response = await LogsRouter().replay(url="https://x/")
    assert response.found is True
    assert response.record is not None
    assert response.record.title == "latest"
    assert response.narrative


@pytest.mark.asyncio
async def test_replay_not_found(_logs_dir: Path) -> None:
    _seed_log(_logs_dir, [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://other/")])
    response = await LogsRouter().replay(url="https://missing/")
    assert response.found is False
    assert response.record is None


@pytest.mark.asyncio
async def test_tail_returns_n_newest(_logs_dir: Path) -> None:
    _seed_log(
        _logs_dir,
        [_make_record(ts=f"2026-05-10T{h:02d}:00:00+00:00", url=f"https://h{h}/") for h in range(5)],
    )
    response = await LogsRouter().tail(n=3)
    assert response.count == 3
    assert response.records[0].url == "https://h4/"


@pytest.mark.asyncio
async def test_tail_with_since(_logs_dir: Path) -> None:
    """`since="1h"` parses and filters."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    _seed_log(
        _logs_dir,
        [
            _make_record(ts=(now - timedelta(hours=10)).isoformat(timespec="milliseconds"), url="https://old/"),
            _make_record(ts=(now - timedelta(minutes=5)).isoformat(timespec="milliseconds"), url="https://new/"),
        ],
    )
    response = await LogsRouter().tail(n=10, since="1h")
    assert response.count == 1
    assert response.records[0].url == "https://new/"


@pytest.mark.asyncio
async def test_grep_returns_matches(_logs_dir: Path) -> None:
    _seed_log(
        _logs_dir,
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/", verdict="paywall"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://b/", verdict="ok"),
        ],
    )
    response = await LogsRouter().grep(pattern="paywall")
    assert response.count == 1
    assert response.records[0].url == "https://a/"


@pytest.mark.asyncio
async def test_tail_invalid_since_raises(_logs_dir: Path) -> None:
    with pytest.raises(ValueError):
        await LogsRouter().tail(n=10, since="not_a_duration")
