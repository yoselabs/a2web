"""NDJSON request log — in-tree microsofware.

Append-only NDJSON writer with lazy-open + size-based rotation + gzip on
rollover. Zero a2web-domain imports. The record shape (`LogRecord`) is
the boundary type; domain-specific construction (e.g. from a
`FetchResponse`) lives at the a2web seam.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

# --------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------- #


def log_dir() -> Path:
    """Resolve the log directory: `$A2WEB_LOG_DIR` if set, else `~/.a2web/logs/`."""
    override = os.environ.get("A2WEB_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".a2web" / "logs"


def active_log_path(now: datetime | None = None) -> Path:
    """Path of the active NDJSON log for the given (or current) date."""
    moment = now or datetime.now(UTC)
    return log_dir() / f"fetches-{moment:%Y-%m-%d}.ndjson"


# --------------------------------------------------------------------- #
# Rotation
# --------------------------------------------------------------------- #


DEFAULT_ROTATION_BYTES = 16 * 1024 * 1024

_ROLLED_NAME_RE = re.compile(r"^fetches-(\d{4}-\d{2}-\d{2})-(\d{2})\.ndjson(?:\.gz)?$")


def next_rolled_path(active: Path, *, now: datetime | None = None) -> Path:
    """Pick the next `fetches-YYYY-MM-DD-NN.ndjson` slot for rollover."""
    moment = now or datetime.now(UTC)
    date_stamp = moment.strftime("%Y-%m-%d")
    parent = active.parent
    used_seqs: set[int] = set()
    if parent.is_dir():
        for entry in parent.iterdir():
            match = _ROLLED_NAME_RE.match(entry.name)
            if match and match.group(1) == date_stamp:
                used_seqs.add(int(match.group(2)))
    next_seq = max(used_seqs, default=0) + 1
    return parent / f"fetches-{date_stamp}-{next_seq:02d}.ndjson"


def gzip_file(src: Path) -> Path:
    """Gzip `src` to `src + ".gz"` and remove the original. Returns the gz path."""
    dst = src.with_suffix(src.suffix + ".gz")
    with src.open("rb") as fin, gzip.open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    src.unlink()
    return dst


# --------------------------------------------------------------------- #
# Record (boundary type)
# --------------------------------------------------------------------- #


def dominant_verdict(diagnostics: list[dict]) -> str:
    """Pick the most informative verdict across diagnostic rows.

    Order of precedence: any non-`ok` verdict wins over `ok`. Last
    non-`ok` value (chronologically last in the list) is the most
    actionable signal.
    """
    non_ok = [d for d in diagnostics if d.get("verdict") not in (None, "ok")]
    if non_ok:
        return str(non_ok[-1]["verdict"])
    return "ok"


@dataclass(slots=True)
class LogRecord:
    ts: str
    url: str
    final_url: str
    host: str
    tier: str
    status: str
    verdict: str
    cache: str
    total_ms: int
    content_chars: int
    diagnostics: list[dict] = field(default_factory=list)
    title: str | None = None
    error: str | None = None

    def to_json(self) -> str:
        """Single-line JSON encoding, no embedded newlines."""
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------- #


if TYPE_CHECKING:
    pass


class LogWriter:
    """Append-only NDJSON writer for fetch records.

    The `disabled` flag turns `write_record` into a no-op without touching
    the filesystem — used when the host opts out of logging.
    """

    _path_factory: Callable[[], Path]
    _handle: Any
    _lock: asyncio.Lock
    _threshold_bytes: int
    _disabled: bool
    _open_path: Path | None

    __slots__ = ("_disabled", "_handle", "_lock", "_open_path", "_path_factory", "_threshold_bytes")

    def __init__(
        self,
        *,
        path_factory: Callable[[], Path] = active_log_path,
        threshold_bytes: int = DEFAULT_ROTATION_BYTES,
        disabled: bool = False,
    ) -> None:
        self._path_factory = path_factory
        self._handle = None
        self._lock = asyncio.Lock()
        self._threshold_bytes = threshold_bytes
        self._disabled = disabled
        self._open_path = None

    async def write_record(self, record: LogRecord) -> None:
        """Append one NDJSON line. Best-effort; rotates on threshold."""
        if self._disabled:
            return
        line = record.to_json() + "\n"
        async with self._lock:
            await self._ensure_open()
            assert self._handle is not None  # noqa: S101 — invariant after _ensure_open
            await self._handle.write(line)
            await self._handle.flush()
            await self._maybe_rotate()

    async def aclose(self) -> None:
        """Close the active handle if open. Tests use this; no production caller."""
        async with self._lock:
            if self._handle is not None:
                await self._handle.close()
                self._handle = None
                self._open_path = None

    async def _ensure_open(self) -> None:
        if self._handle is not None:
            return
        path = self._path_factory()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = await aiofiles.open(path, mode="a", encoding="utf-8")
        self._open_path = path

    async def _maybe_rotate(self) -> None:
        if self._open_path is None:
            return
        try:
            size = self._open_path.stat().st_size
        except OSError:
            return
        if size < self._threshold_bytes:
            return

        if self._handle is not None:
            await self._handle.close()
            self._handle = None
        rolled = next_rolled_path(self._open_path)
        self._open_path.rename(rolled)
        await asyncio.to_thread(gzip_file, rolled)
        self._open_path = None


__all__ = (
    "DEFAULT_ROTATION_BYTES",
    "LogRecord",
    "LogWriter",
    "active_log_path",
    "dominant_verdict",
    "gzip_file",
    "log_dir",
    "next_rolled_path",
)
