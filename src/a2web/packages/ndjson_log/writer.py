"""NDJSON writer with lazy-open + size-based rotation + gzip on rollover.

One writer per host application. Writes serialize on an asyncio lock.
Construction does not touch the filesystem; the file is opened on first
`write_record`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

from .paths import active_log_path
from .rotation import DEFAULT_ROTATION_BYTES, gzip_file, next_rolled_path

if TYPE_CHECKING:
    from .record import LogRecord


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
