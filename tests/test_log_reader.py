"""Log reader — iter, find_last_for_url, grep, tail."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from a2web.log.reader import find_last_for_url, grep_records, iter_records, tail_records


def _make_record(*, ts: str, url: str, host: str = "example.com", verdict: str = "ok", title: str | None = None) -> dict:
    return {
        "ts": ts,
        "url": url,
        "final_url": url,
        "host": host,
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


def _write_lines(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _write_gz(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_iter_records_yields_in_order(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://b/"),
        ],
    )
    out = list(iter_records(directory=tmp_path))
    assert [r.url for r in out] == ["https://a/", "https://b/"]


def test_find_last_for_url_returns_newest_match(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://x/"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://x/", title="latest"),
            _make_record(ts="2026-05-10T11:00:00+00:00", url="https://other/"),
        ],
    )
    found = find_last_for_url("https://x/", directory=tmp_path)
    assert found is not None
    assert found.title == "latest"


def test_find_last_for_url_no_match(tmp_path: Path) -> None:
    _write_lines(tmp_path / "fetches-2026-05-10.ndjson", [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/")])
    assert find_last_for_url("https://missing/", directory=tmp_path) is None


def test_grep_returns_matches_newest_first(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/", verdict="paywall"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://b/", verdict="ok"),
            _make_record(ts="2026-05-10T11:00:00+00:00", url="https://c/", verdict="paywall"),
        ],
    )
    matches = grep_records("paywall", directory=tmp_path)
    assert [r.url for r in matches] == ["https://c/", "https://a/"]


def test_grep_case_insensitive(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/", title="Important Article")],
    )
    matches = grep_records("important", directory=tmp_path)
    assert len(matches) == 1


def test_gzipped_rolled_files_are_read(tmp_path: Path) -> None:
    _write_gz(
        tmp_path / "fetches-2026-05-09.ndjson.gz",
        [_make_record(ts="2026-05-09T12:00:00+00:00", url="https://yesterday/")],
    )
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://today/")],
    )
    out = list(iter_records(directory=tmp_path))
    urls = [r.url for r in out]
    assert "https://yesterday/" in urls
    assert "https://today/" in urls


def test_malformed_lines_skipped(tmp_path: Path) -> None:
    path = tmp_path / "fetches-2026-05-10.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/")) + "\n")
        fh.write("not json at all\n")
        fh.write(json.dumps({"missing": "fields"}) + "\n")  # parses but fails record build
        fh.write(json.dumps(_make_record(ts="2026-05-10T10:00:00+00:00", url="https://b/")) + "\n")
    out = list(iter_records(directory=tmp_path))
    assert [r.url for r in out] == ["https://a/", "https://b/"]


def test_tail_returns_n_newest(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [_make_record(ts=f"2026-05-10T{h:02d}:00:00+00:00", url=f"https://h{h}/") for h in range(5)],
    )
    out = tail_records(n=3, directory=tmp_path)
    assert [r.url for r in out] == ["https://h4/", "https://h3/", "https://h2/"]


def test_iter_with_since_filters(tmp_path: Path) -> None:
    """Records older than `since` are filtered out."""
    now = datetime.now(UTC)
    old_ts = (now - timedelta(hours=10)).isoformat(timespec="milliseconds")
    new_ts = (now - timedelta(minutes=5)).isoformat(timespec="milliseconds")
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [
            _make_record(ts=old_ts, url="https://old/"),
            _make_record(ts=new_ts, url="https://new/"),
        ],
    )
    out = list(iter_records(since=timedelta(hours=1), directory=tmp_path))
    assert [r.url for r in out] == ["https://new/"]


def test_grep_empty_pattern_returns_empty(tmp_path: Path) -> None:
    _write_lines(tmp_path / "fetches-2026-05-10.ndjson", [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/")])
    assert grep_records("", directory=tmp_path) == []


def test_iter_filter_by_host(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "fetches-2026-05-10.ndjson",
        [
            _make_record(ts="2026-05-10T09:00:00+00:00", url="https://a.example/", host="a.example"),
            _make_record(ts="2026-05-10T10:00:00+00:00", url="https://b.example/", host="b.example"),
        ],
    )
    out = list(iter_records(host="a.example", directory=tmp_path))
    assert len(out) == 1
    assert out[0].host == "a.example"


def test_missing_directory_returns_empty(tmp_path: Path) -> None:
    out = list(iter_records(directory=tmp_path / "does_not_exist"))
    assert out == []


def test_tail_with_zero_returns_empty(tmp_path: Path) -> None:
    _write_lines(tmp_path / "fetches-2026-05-10.ndjson", [_make_record(ts="2026-05-10T09:00:00+00:00", url="https://a/")])
    assert tail_records(n=0, directory=tmp_path) == []
