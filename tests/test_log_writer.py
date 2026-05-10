"""LogWriter — lazy-open, concurrent writes, rotation, disabled mode."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import pytest

from a2web.log.record import LogRecord
from a2web.log.writer import LogWriter


def _make_record(i: int = 0) -> LogRecord:
    return LogRecord(
        ts="2026-05-09T19:00:00.000+00:00",
        url=f"https://example.com/{i}",
        final_url=f"https://example.com/{i}",
        host="example.com",
        tier="raw",
        status="ok",
        verdict="ok",
        cache="miss",
        total_ms=100,
        content_chars=1000,
    )


@pytest.mark.asyncio
async def test_construction_does_not_create_file(tmp_path: Path) -> None:
    target = tmp_path / "fetches.ndjson"
    LogWriter(path_factory=lambda: target)
    assert not target.exists()


@pytest.mark.asyncio
async def test_first_write_creates_dir_and_file(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "fetches.ndjson"
    writer = LogWriter(path_factory=lambda: target)
    await writer.write_record(_make_record())
    await writer.aclose()

    assert target.parent.is_dir()
    content = target.read_text()
    assert content.endswith("\n")
    parsed = json.loads(content.strip())
    assert parsed["url"] == "https://example.com/0"


@pytest.mark.asyncio
async def test_concurrent_writes_serialize(tmp_path: Path) -> None:
    target = tmp_path / "fetches.ndjson"
    writer = LogWriter(path_factory=lambda: target)

    await asyncio.gather(*(writer.write_record(_make_record(i)) for i in range(10)))
    await writer.aclose()

    lines = [line for line in target.read_text().splitlines() if line]
    assert len(lines) == 10
    parsed = [json.loads(line) for line in lines]
    urls = {p["url"] for p in parsed}
    assert urls == {f"https://example.com/{i}" for i in range(10)}


@pytest.mark.asyncio
async def test_disabled_writer_is_noop(tmp_path: Path) -> None:
    target = tmp_path / "fetches.ndjson"
    writer = LogWriter(path_factory=lambda: target, disabled=True)
    for i in range(5):
        await writer.write_record(_make_record(i))
    assert not target.exists()


@pytest.mark.asyncio
async def test_rotation_on_size_threshold(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    target = tmp_path / f"fetches-{today}.ndjson"
    writer = LogWriter(path_factory=lambda: target, threshold_bytes=200)

    # Each line ~120 bytes; two writes will cross the 200B threshold.
    for i in range(3):
        await writer.write_record(_make_record(i))
    await writer.aclose()

    rolled = list(tmp_path.glob(f"fetches-{today}-*.ndjson.gz"))  # noqa: ASYNC240
    assert len(rolled) >= 1, list(tmp_path.iterdir())  # noqa: ASYNC240

    # Decompress and confirm at least one record made it
    with gzip.open(rolled[0], "rt") as fh:
        gz_lines = [line for line in fh.read().splitlines() if line]
    assert all(json.loads(line)["url"].startswith("https://example.com/") for line in gz_lines)


@pytest.mark.asyncio
async def test_multiple_rollovers_increment_sequence(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    target = tmp_path / f"fetches-{today}.ndjson"
    writer = LogWriter(path_factory=lambda: target, threshold_bytes=120)

    for i in range(8):
        await writer.write_record(_make_record(i))
    await writer.aclose()

    rolled = sorted(tmp_path.glob(f"fetches-{today}-*.ndjson.gz"))  # noqa: ASYNC240
    assert len(rolled) >= 2
    seqs = [int(p.stem.split("-")[-1].removesuffix(".ndjson")) for p in rolled]
    assert seqs == sorted(set(seqs))  # unique, monotonic
