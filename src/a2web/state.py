"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on. PR7a
swaps PR3's per-fetch sqlite open for a *lazy singleton*: the first
fetch on a given AppState opens the connection under an asyncio.Lock,
caches it on `state.sqlite`, and reuses it. An atexit hook closes the
connection on a fresh loop at process shutdown.

a2kit v0.23 has no lifespan hook (FastMCP's `lifespan=` kwarg is not
forwarded by `a2kit.run`), so the framework can't own this. Lazy +
atexit lands the same effect for both CLI and MCP entry paths.
"""

from __future__ import annotations

import asyncio
import atexit
from dataclasses import dataclass, field
from typing import Any

import a2kit
import aiosqlite
from purgatory import AsyncCircuitBreakerFactory

from .cache.sqlite_cache import open_sqlite_with_schema
from .log.writer import LogWriter
from .settings import AppSettings, get_settings


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton."""

    settings: AppSettings
    sqlite: aiosqlite.Connection | None = None
    breakers: AsyncCircuitBreakerFactory | None = None
    log_writer: LogWriter | None = None
    proxy_pool: Any | None = None
    browser_pool: Any | None = None
    sqlite_lock: asyncio.Lock | None = None
    browser_lock: asyncio.Lock | None = None
    proxy_lock: asyncio.Lock | None = None
    extras: dict[str, Any] = field(default_factory=dict)


async def ensure_sqlite(state: AppState) -> aiosqlite.Connection:
    """Open sqlite on first call; return cached connection thereafter."""
    if state.sqlite is not None:
        return state.sqlite
    if state.sqlite_lock is None:
        state.sqlite_lock = asyncio.Lock()
    async with state.sqlite_lock:
        if state.sqlite is None:
            state.sqlite = await open_sqlite_with_schema(state.settings)
    return state.sqlite


async def ensure_proxy_pool(state: AppState) -> Any:
    """Open ProxyPool on first call; return cached pool thereafter.

    Pure resolution does not need the pool (it's stateless), but the
    health/quarantine state is per-AppState and lives here.
    """
    if state.proxy_pool is not None:
        return state.proxy_pool
    if state.proxy_lock is None:
        state.proxy_lock = asyncio.Lock()
    async with state.proxy_lock:
        if state.proxy_pool is None:
            from .proxy.pool import ProxyPool
            state.proxy_pool = ProxyPool(settings=state.settings)
    return state.proxy_pool


async def ensure_browser_pool(state: AppState) -> Any:
    """Open Camoufox pool on first call; return cached pool thereafter.

    Imports Camoufox lazily so the optional dep is only paid when the
    browser tier is actually invoked. On ImportError, raises so the
    caller (BrowserTier) can translate to a graceful operator hint.
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


def _atexit_close(state: AppState) -> None:
    """Best-effort resource close at process exit (sqlite + browser pool)."""
    conn = state.sqlite
    pool = state.browser_pool
    if conn is None and pool is None:
        return
    try:
        loop = asyncio.new_event_loop()
        try:
            if conn is not None:
                loop.run_until_complete(conn.close())
            if pool is not None:
                loop.run_until_complete(pool.close())
        finally:
            loop.close()
    except Exception:  # best-effort; WAL is durable on disk
        return
    state.sqlite = None
    state.browser_pool = None


def register_state(app: a2kit.App, *, settings: AppSettings | None = None) -> a2kit.App:
    """Attach a per-App `AppState` singleton to `app`'s DI container."""
    resolved = settings or get_settings()
    state = AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
    )
    atexit.register(_atexit_close, state)
    app.provide(AppState, lambda: state)
    return app


async def bootstrap_state_for_test(settings: AppSettings | None = None) -> AppState:
    """Test fixture: build an AppState with sqlite pre-opened."""
    resolved = settings or get_settings()
    state = AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
    )
    await ensure_sqlite(state)
    return state


async def teardown_state_for_test(state: AppState) -> None:
    """Test fixture: close sqlite + browser pool cleanly."""
    if state.sqlite is not None:
        await state.sqlite.close()
        state.sqlite = None
    if state.browser_pool is not None:
        await state.browser_pool.close()
        state.browser_pool = None
