"""Camoufox browser pool — per-host contexts, LRU eviction, page-per-fetch.

Resource pattern (a2kit v0.27 canonical):
- Sync `__init__`: does not launch Firefox.
- `_ensure()`: idempotent under internal `_lock` with double-checked
  open. Lazy-launches Camoufox on first call. Concurrent first-fetches
  share one launch.
- `close()`: idempotent; called from `@app.on_shutdown`.

AppState holds the pool as a **non-Optional** field. Callers do not
ensure externally — `BrowserTier.fetch()` invokes `_ensure()` itself and
catches `ImportError` from a missing `[browser]` extra.

Concurrency:
- Per-host BrowserContext keeps cookies warm across same-host fetches.
- Pages are 1:1 per fetch (created in `acquire`, closed in `release`).
- An `asyncio.Lock` guards the contexts dict + LRU order.
- Idle eviction runs on every acquire (cheap; no background task).

Resource budget:
- Page wall-clock and bytes-transferred caps are enforced by the tier
  (BrowserTier wraps `goto` in `asyncio.wait_for`); the pool itself
  doesn't time out — keeping the timeout near the I/O is cleaner.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine


class _StderrFilenoShim:
    """Stand-in for ``sys.stderr`` that lies only about its file descriptor.

    Playwright spawns its Node driver with ``stderr=_get_stderr_fileno()``,
    which reads ``sys.stderr.fileno()`` at spawn time (see playwright
    ``_impl/_transport.py``). Swapping ``sys.stderr`` for this shim around the
    launch makes the driver subprocess inherit our pipe's write end — and
    nothing else: every attribute except ``fileno`` delegates to the real
    stream, so Python-level ``sys.stderr.write``/``flush`` and any
    ``StreamHandler`` still reach the genuine terminal. Confines the redirect
    to the spawned child; the parent's fd 2 is never touched.
    """

    def __init__(self, real: Any, fileno: int) -> None:
        self._real = real
        self._fileno = fileno

    def fileno(self) -> int:
        return self._fileno

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class BrowserPool:
    """Per-host Camoufox contexts with LRU eviction.

    Not thread-safe; assumes a single asyncio event loop (the standard
    a2web invariant).
    """

    def __init__(
        self,
        *,
        max_pool: int = 4,
        idle_timeout_s: int = 300,
        page_budget_s: int = 30,
        stderr_sink: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.max_pool = max_pool
        self.idle_timeout_s = idle_timeout_s
        self.page_budget_s = page_budget_s
        # Insertion order = LRU (move-to-end on touch).
        self._contexts: OrderedDict[str, _HostContext] = OrderedDict()
        self._camoufox: Any | None = None
        self._browser: Any | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._eviction_tasks: set[asyncio.Task[None]] = set()
        # Driver-stderr capture (opt-in via injected async sink — keeps this
        # package domain-free; the domain wires emission of typed log events).
        self._stderr_sink = stderr_sink
        self._stderr_read_fd: int | None = None
        self._stderr_write_fd: int = -1
        self._stderr_buf = b""
        self._stderr_loop: asyncio.AbstractEventLoop | None = None
        self._stderr_tasks: set[asyncio.Task[None]] = set()

    async def _ensure(self) -> None:
        """Lazy-init: launch Camoufox under lock if not yet opened.

        Idempotent under concurrent first calls (double-checked locking).
        Raises ImportError if optional dep missing — BrowserTier catches
        and translates to operator hint.
        """
        if self._browser is not None:
            return
        async with self._lock:
            if self._browser is not None:
                return
            # Lazy import — keeps base install lean; ImportError bubbles up.
            from camoufox.async_api import AsyncCamoufox

            self._camoufox = AsyncCamoufox(headless=True)
            # AsyncCamoufox is itself an async context manager; we hold the
            # Browser handle for the pool's lifetime. Redirect the driver's
            # inherited stderr into a pipe across the launch so raw Node.js
            # traces never hit the operator's terminal (no-op without a sink).
            saved_stderr = self._install_stderr_capture()
            try:
                self._browser = await self._camoufox.__aenter__()
            finally:
                self._restore_stderr(saved_stderr)
            self._begin_stderr_drain()

    def _install_stderr_capture(self) -> Any:
        """Swap `sys.stderr` for a pipe-backed shim across the driver launch.

        Returns the real `sys.stderr` to restore, or None when capture is off
        (no sink injected — test pools keep their inherited stderr untouched).
        """
        if self._stderr_sink is None:
            return None
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        self._stderr_read_fd = read_fd
        self._stderr_write_fd = write_fd
        real = sys.stderr
        sys.stderr = _StderrFilenoShim(real, write_fd)  # type: ignore[assignment]
        return real

    def _restore_stderr(self, saved: Any) -> None:
        """Restore `sys.stderr` and drop the parent's copy of the pipe writer.

        After the driver subprocess has spawned (inheriting its own dup of the
        write end), the parent must close its writer so the reader EOFs when
        the driver eventually exits.
        """
        if self._stderr_sink is None or self._stderr_read_fd is None:
            return
        sys.stderr = saved  # type: ignore[assignment]
        with suppress(OSError):
            os.close(self._stderr_write_fd)

    def _begin_stderr_drain(self) -> None:
        """Register an on-loop reader that forwards driver stderr lines."""
        if self._stderr_sink is None or self._stderr_read_fd is None:
            return
        self._stderr_loop = asyncio.get_running_loop()
        self._stderr_loop.add_reader(self._stderr_read_fd, self._on_stderr_readable)

    def _on_stderr_readable(self) -> None:
        """Drain available driver stderr bytes; emit each complete line."""
        read_fd = self._stderr_read_fd
        if read_fd is None:
            return
        try:
            chunk = os.read(read_fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            self._stop_stderr_capture()
            return
        if not chunk:  # EOF — driver subprocess exited and closed its stderr.
            self._stop_stderr_capture()
            return
        self._stderr_buf += chunk
        *lines, self._stderr_buf = self._stderr_buf.split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line:
                self._emit_stderr_line(line)

    def _emit_stderr_line(self, line: str) -> None:
        sink = self._stderr_sink
        loop = self._stderr_loop
        if sink is None or loop is None:
            return
        task = loop.create_task(sink(line))
        self._stderr_tasks.add(task)
        task.add_done_callback(self._stderr_tasks.discard)

    def _stop_stderr_capture(self) -> None:
        """Tear down the reader and close the pipe read end. Idempotent."""
        read_fd = self._stderr_read_fd
        if read_fd is None:
            return
        if self._stderr_buf:  # flush a trailing unterminated line
            line = self._stderr_buf.decode("utf-8", "replace").rstrip("\r")
            self._stderr_buf = b""
            if line:
                self._emit_stderr_line(line)
        if self._stderr_loop is not None:
            with suppress(Exception):
                self._stderr_loop.remove_reader(read_fd)
        with suppress(OSError):
            os.close(read_fd)
        self._stderr_read_fd = None

    async def start(self) -> None:
        """Deprecated alias for `_ensure()`. Kept during v0.27 migration."""
        await self._ensure()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_stderr_capture()
        async with self._lock:
            for host_ctx in list(self._contexts.values()):
                with suppress(Exception):
                    await host_ctx.context.close()
            self._contexts.clear()
        if self._camoufox is not None:
            with suppress(Exception):
                await self._camoufox.__aexit__(None, None, None)
            self._camoufox = None
            self._browser = None

    # Framework-facing async-CM protocol (a2kit v0.36+). Thin wrappers around
    # the existing idempotent `_ensure` / `close` internal surface.
    async def __aenter__(self) -> BrowserPool:
        await self._ensure()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    @asynccontextmanager
    async def acquire(self, url: str) -> AsyncIterator[Any]:
        """Yield a fresh page for `url`'s host. Closes the page on exit.

        The host's BrowserContext is reused across fetches (cookie jar
        warm); only the Page is per-fetch (1:1 to avoid state leak).
        """
        host = urlparse(url).hostname or "_default"
        page = await self._open_page(host)
        try:
            yield page
        finally:
            with suppress(Exception):
                await page.close()

    async def _open_page(self, host: str) -> Any:
        async with self._lock:
            self._evict_idle_locked()
            host_ctx = self._contexts.get(host)
            if host_ctx is None:
                host_ctx = await self._create_host_context_locked(host)
            else:
                self._contexts.move_to_end(host)
            host_ctx.last_used = time.monotonic()
            page = await host_ctx.context.new_page()
            return page

    async def _create_host_context_locked(self, host: str) -> _HostContext:
        if self._browser is None:
            raise RuntimeError("BrowserPool.start() not called")
        # LRU evict if at cap.
        while len(self._contexts) >= self.max_pool:
            evicted_host, evicted = self._contexts.popitem(last=False)
            with suppress(Exception):
                await evicted.context.close()
            del evicted_host
        context = await self._browser.new_context()
        host_ctx = _HostContext(context=context, last_used=time.monotonic())
        self._contexts[host] = host_ctx
        return host_ctx

    def _evict_idle_locked(self) -> None:
        now = time.monotonic()
        stale = [h for h, c in self._contexts.items() if now - c.last_used > self.idle_timeout_s]
        for host in stale:
            ctx = self._contexts.pop(host)
            # Close-fire-and-forget; we're under the lock so can't await.
            # Keep a reference so the task is not garbage-collected mid-close.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                continue
            task = loop.create_task(_safe_close(ctx.context))
            self._eviction_tasks.add(task)
            task.add_done_callback(self._eviction_tasks.discard)


class _HostContext:
    __slots__ = ("context", "last_used")

    def __init__(self, *, context: Any, last_used: float) -> None:
        self.context = context
        self.last_used = last_used


async def _safe_close(context: Any) -> None:
    with suppress(Exception):
        await context.close()
