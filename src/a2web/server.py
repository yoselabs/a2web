"""a2web server entrypoint — `a2kit.App` composition.

Imperative composition (per the v0.26 README convention): build the App, add
the router, register the singleton, declare lifecycle hooks + health check +
OTel sink. No `connections_cli` — a2web has no per-instance connection
concept.
"""

from __future__ import annotations

import a2kit

from .cache.sqlite_cache import open_sqlite_with_schema
from .events import otel_sink
from .events.types import StageEnded, StageStarted, TierEnded, TierHeartbeat, TierStarted
from .routers import WebRouter
from .state import AppState, build_state

app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())
app.singleton(AppState, factory=build_state)

# Register typed event payloads so a2kit can route them through the typed-emit
# path (one call emits dump → event → progress).
app.ldd.events.register(TierStarted)
app.ldd.events.register(TierEnded)
app.ldd.events.register(StageStarted)
app.ldd.events.register(StageEnded)
app.ldd.events.register(TierHeartbeat)

# OTel sink runs sequentially after the wire emit, best-effort under
# cancellation (a2kit logs exceptions to a2kit.ldd.sinks).
app.ldd.add_sink(otel_sink)


@app.on_startup
async def _open_resources(_app: a2kit.App) -> None:
    """Open sqlite + warm the cache schema before the first dispatch."""
    container = _app.container()
    if container is None:
        msg = "container() must be initialized after singleton(...) is registered"
        raise RuntimeError(msg)
    state = await container.resolve(AppState, connection=None)
    state.sqlite = await open_sqlite_with_schema(state.settings)


@app.on_shutdown
async def _close_resources(_app: a2kit.App) -> None:
    """Close sqlite + browser pool (if launched) at process exit."""
    container = _app.container()
    if container is None:
        msg = "container() must be initialized after singleton(...) is registered"
        raise RuntimeError(msg)
    state = await container.resolve(AppState, connection=None)
    if state.sqlite is not None:
        await state.sqlite.close()
        state.sqlite = None
    if state.browser_pool is not None:
        await state.browser_pool.close()
        state.browser_pool = None


@app.health_check
async def _check_sqlite(state: AppState) -> a2kit.HealthResult:
    """Readiness probe for `_meta.health` / `a2web health`."""
    if state.sqlite is None:
        return a2kit.HealthResult.fail("sqlite not opened")
    return a2kit.HealthResult.ok()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
