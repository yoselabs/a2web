"""Camoufox browser pool — per-host contexts, LRU eviction, page-per-fetch.

Pool ownership pattern (mirrors PR7a sqlite):
- Lazy: `BrowserPool.__init__` does not launch Firefox; `start()` does.
- Singleton-per-AppState: `state.ensure_browser_pool` caches the pool
  under an asyncio.Lock so concurrent first-fetches share one pool.
- atexit-cleaned: `state._atexit_close` calls `pool.close()` on a fresh
  event loop at process exit.

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
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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

    async def start(self) -> None:
        """Launch Camoufox. Raises ImportError if optional dep missing."""
        if self._browser is not None:
            return
        # Lazy import — keeps base install lean; ImportError bubbles up so
        # BrowserTier can translate to operator hint.
        from camoufox.async_api import AsyncCamoufox

        self._camoufox = AsyncCamoufox(headless=True)
        # AsyncCamoufox is itself an async context manager; we hold the
        # Browser handle for the pool's lifetime.
        self._browser = await self._camoufox.__aenter__()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
