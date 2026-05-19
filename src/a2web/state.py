"""Per-App shared state — always-on resource bundle.

`AppState` carries the four resources every fetch needs: settings, breakers,
proxy_pool, sqlite. Heavy/conditional resources (browser_pool, llm_extractor)
are independently provided by a2kit v0.36+ DI and surfaced at the tool seam
as `Lazy[T]` so the cold-start cost is paid only when the path needs them.

Lifecycle is owned by a2kit v0.36+: each resource registered via
`app.provide(...)` enters on first resolution (lazy first-use) and exits in
LIFO order on app shutdown. Resources expose `__aenter__`/`__aexit__` as
thin wrappers around their existing idempotent `_ensure()` / `close()`
methods (kept as the internal lazy-call surface).

AppState fields are non-Optional. Locks live inside resources, never on
AppState. AppState itself is a pure data bundle — no `__aenter__` needed
(framework gracefully skips singletons that don't expose the CM protocol).
"""

from __future__ import annotations

from dataclasses import dataclass

from purgatory import AsyncCircuitBreakerFactory

from .packages.http_cache import SqliteResource
from .packages.proxy_routing import ProxyPool
from .settings import AppSettings


@dataclass(slots=True)
class AppState:
    """Always-on resources for the fetch pipeline. Per-App singleton.

    `browser_pool` and `llm_extractor` are NOT here — they're independent
    providers surfaced at the tool seam via `Lazy[T]` (see `routers.py`).
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    proxy_pool: ProxyPool
    sqlite: SqliteResource


def build_state(
    settings: AppSettings,
    breakers: AsyncCircuitBreakerFactory,
    proxy_pool: ProxyPool,
    sqlite: SqliteResource,
) -> AppState:
    """Bundle the four always-on resources into AppState.

    The container chain-resolves each dep via its own provider registered
    in `server.py`. No I/O here — each resource opens lazily on first use
    via its `__aenter__`.
    """
    return AppState(
        settings=settings,
        breakers=breakers,
        proxy_pool=proxy_pool,
        sqlite=sqlite,
    )
