"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on. Lifecycle is
owned by a2kit v0.27+ via DI-aware `@app.on_startup` / `@app.on_shutdown` /
`@app.health_check` hooks plus `app.singleton(AppState, build_state)` — see
`server.py` for the wiring.

Resource pattern (a2kit v0.27 canonical): every long-lived resource is a
class with sync `__init__`, internal `_lock`, lazy `_ensure()`, and
idempotent `close()`. AppState fields are **non-Optional**. Locks live
inside resources, never on AppState.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from purgatory import AsyncCircuitBreakerFactory

from .llm_resource import LlmExtractorResource
from .packages.browser_pool import BrowserPool
from .packages.http_cache import SqliteResource
from .packages.ndjson_log import LogWriter
from .packages.proxy_routing import ProxyEntryShape, ProxyPool, RouteRuleShape
from .settings import AppSettings, get_settings


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton.

    Every field is non-Optional. Resources that need an event loop to open
    (sqlite, browser, LLM extractor) are wrapped in Resource classes that
    self-initialize on first use under their own internal locks.
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    log_writer: LogWriter
    proxy_pool: ProxyPool
    sqlite: SqliteResource
    browser_pool: BrowserPool
    llm_extractor: LlmExtractorResource


def build_state(settings: AppSettings | None = None) -> AppState:
    """Factory for the AppState singleton. Sync — a2kit v0.27 requires this.

    Every resource is constructed cheaply here (no I/O). Async opens happen
    on first use via each resource's `_ensure()`.
    """
    resolved = settings or get_settings()
    sqlite = SqliteResource(db_path=None)
    return AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
        proxy_pool=ProxyPool(
            routes=cast("list[RouteRuleShape]", resolved.routes),
            proxies=cast("dict[str, ProxyEntryShape]", resolved.proxies),
        ),
        sqlite=sqlite,
        browser_pool=BrowserPool(
            max_pool=resolved.browser_max_pool,
            idle_timeout_s=resolved.browser_idle_timeout_s,
            page_budget_s=resolved.browser_page_budget_s,
        ),
        llm_extractor=LlmExtractorResource(resolved, sqlite),
    )
