"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on. PR3
opens the sqlite cache per-fetch (aiosqlite worker threads block the
event loop's clean teardown when reused across `asyncio.run()` calls).
The breakers factory is synchronous and lives on `AppState.breakers`.

`register_state(app, *, settings=None)` registers a closure provider so the
container hands the same `AppState` to every dispatch on a given App.

PR4 will replace per-fetch open/close with a proper FastMCP lifespan +
anyio TaskGroup that owns the sqlite + log writer + pool lifecycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import a2kit
import aiosqlite
from purgatory import AsyncCircuitBreakerFactory

from .cache.sqlite_cache import open_sqlite_with_schema
from .settings import AppSettings, get_settings


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton.

    `sqlite` is `None` at construction. The orchestrator opens a fresh
    aiosqlite connection for each fetch and closes it before returning;
    PR4 replaces this with a long-lived connection managed by a
    lifespan hook.
    """

    settings: AppSettings
    sqlite: aiosqlite.Connection | None = None
    breakers: AsyncCircuitBreakerFactory | None = None
    log_writer: Any | None = None
    proxy_pool: Any | None = None
    browser_pool: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)


async def open_sqlite(state: AppState) -> aiosqlite.Connection:
    """Open a fresh sqlite connection bound to the current event loop."""
    return await open_sqlite_with_schema(state.settings)


def register_state(app: a2kit.App, *, settings: AppSettings | None = None) -> a2kit.App:
    """Attach a per-App `AppState` singleton to `app`'s DI container."""
    resolved = settings or get_settings()
    state = AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
    )
    app.provide(AppState, lambda: state)
    return app
