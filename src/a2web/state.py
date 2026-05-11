"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on. Lifecycle is
owned by a2kit v0.26+ via `@app.on_startup` / `@app.on_shutdown` hooks plus
`app.singleton(AppState, factory=build_state)` — see `server.py` for the wiring.

Browser pool stays lazily opened inside `BrowserTier.fetch` (Camoufox is an
optional dep; we must not crash startup if it's missing).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite
from purgatory import AsyncCircuitBreakerFactory

from .log.writer import LogWriter
from .proxy.pool import ProxyPool
from .settings import AppSettings, get_settings

if TYPE_CHECKING:
    from .browser.pool import BrowserPool


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton.

    `sqlite` is assigned by the `@app.on_startup` hook (requires event loop).
    `browser_pool` stays None and is lazily opened on first browser-tier
    dispatch (Camoufox is an optional dep).
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    log_writer: LogWriter
    proxy_pool: ProxyPool
    sqlite: aiosqlite.Connection | None = None
    browser_pool: BrowserPool | None = None
    browser_lock: asyncio.Lock | None = None


def build_state(settings: AppSettings | None = None) -> AppState:
    """Factory for the AppState singleton. Sqlite is opened in @on_startup."""
    resolved = settings or get_settings()
    return AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
        proxy_pool=ProxyPool(settings=resolved),
    )


async def ensure_browser_pool(state: AppState):
    """Open Camoufox pool on first call; return cached pool thereafter.

    Stays lazy because Camoufox is an optional dep — opening at startup would
    crash apps that don't have the [browser] extras installed. ImportError
    propagates to the caller (BrowserTier translates to a graceful operator
    hint).
    """
    if state.browser_pool is not None:
        return state.browser_pool
    if state.browser_lock is None:
        state.browser_lock = asyncio.Lock()
    async with state.browser_lock:
        if state.browser_pool is None:
            from .browser.pool import BrowserPool  # local — optional dep

            pool = BrowserPool(
                max_pool=state.settings.browser_max_pool,
                idle_timeout_s=state.settings.browser_idle_timeout_s,
                page_budget_s=state.settings.browser_page_budget_s,
            )
            await pool.start()
            state.browser_pool = pool
    return state.browser_pool
