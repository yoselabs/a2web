"""Read-only access to the NDJSON request log.

Pure-sync functions over `log_dir()`. Routers wrap calls in
`asyncio.to_thread` once. Walks both active `fetches-YYYY-MM-DD.ndjson`
and rolled `fetches-YYYY-MM-DD.ndjson.gz` files.

Malformed lines (invalid JSON, missing required fields) are skipped
silently — the log is best-effort by design (PR4) and a single bad
write should not break read tools.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .paths import log_dir
from .record import LogRecord


def _open_text(path: Path) -> Any:
    """Open `.ndjson` or `.ndjson.gz` as a text-mode file handle."""
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _list_log_files(directory: Path) -> list[Path]:
    """All `fetches-*.ndjson[.gz]` files, oldest-first by mtime."""
    if not directory.is_dir():
        return []
    candidates: list[Path] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if not name.startswith("fetches-"):
            continue
        if name.endswith(".ndjson") or name.endswith(".ndjson.gz"):
            candidates.append(entry)
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates


def _record_from_obj(obj: Any) -> LogRecord | None:
    """Build a LogRecord from a parsed JSON object; return None on shape mismatch."""
    if not isinstance(obj, dict):
        return None
    try:
        return LogRecord(
            ts=str(obj["ts"]),
            url=str(obj["url"]),
            final_url=str(obj.get("final_url", obj["url"])),
            host=str(obj.get("host", "")),
            tier=str(obj.get("tier", "none")),
            status=str(obj.get("status", "failed")),
            verdict=str(obj.get("verdict", "other")),
            cache=str(obj.get("cache", "miss")),
            total_ms=int(obj.get("total_ms", 0)),
            content_chars=int(obj.get("content_chars", 0)),
            diagnostics=list(obj.get("diagnostics", [])),
            title=obj.get("title"),
            error=obj.get("error"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def iter_records(
    *,
    since: timedelta | None = None,
    host: str | None = None,
    directory: Path | None = None,
) -> Iterator[LogRecord]:
    """Yield records oldest-to-newest, optionally filtered."""
    directory = directory or log_dir()
    cutoff: datetime | None = None
    if since is not None:
        cutoff = datetime.now(UTC) - since

    for path in _list_log_files(directory):
        try:
            with _open_text(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record = _record_from_obj(obj)
                    if record is None:
                        continue
                    if host is not None and record.host != host:
                        continue
                    if cutoff is not None:
                        ts = _parse_ts(record.ts)
                        if ts is None or ts < cutoff:
                            continue
                    yield record
        except OSError:
            continue


def find_last_for_url(url: str, *, directory: Path | None = None) -> LogRecord | None:
    """Return the newest record whose `url` exactly matches, or None."""
    last: LogRecord | None = None
    for record in iter_records(directory=directory):
        if record.url == url:
            last = record
    return last


def grep_records(
    pattern: str,
    *,
    limit: int = 50,
    directory: Path | None = None,
) -> list[LogRecord]:
    """Case-insensitive substring search against the serialized record."""
    if not pattern:
        return []
    needle = re.compile(re.escape(pattern), re.IGNORECASE)
    matches: list[LogRecord] = []
    for record in iter_records(directory=directory):
        if needle.search(record.to_json()):
            matches.append(record)
    # newest-first slice
    matches.reverse()
    return matches[:limit]


def tail_records(
    *,
    n: int = 20,
    since: timedelta | None = None,
    directory: Path | None = None,
) -> list[LogRecord]:
    """Return the last `n` records (newest-first)."""
    if n <= 0:
        return []
    collected = list(iter_records(since=since, directory=directory))
    collected.reverse()
    return collected[:n]


__all__ = ["find_last_for_url", "grep_records", "iter_records", "tail_records"]
