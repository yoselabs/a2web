"""a2web server entrypoint — `a2kit.App` composition.

Imperative composition (per the v0.27 README convention): build the App, add
the router, register the singleton, declare DI-aware lifecycle hooks + health
check + OTel sink. No `connections_cli` — a2web has no per-instance
connection concept.
"""

from __future__ import annotations

import a2kit
import a2kit.ldd

from .events import otel_sink
from .events.types import StageEnded, StageStarted, TierEnded, TierHeartbeat, TierStarted
from .routers import WebRouter
from .state import AppState, build_state

app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())
app.singleton(AppState, build_state)

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
async def _open_resources(state: AppState) -> None:
    """Fail-fast warm-up — surface sqlite config errors at startup."""
    await state.sqlite._ensure()


@app.on_shutdown
async def _close_resources(state: AppState) -> None:
    """Close every Resource. Each `close()` is idempotent."""
    await state.sqlite.close()
    await state.browser_pool.close()
    await state.llm_extractor.close()


@app.health_check
async def _check_sqlite(state: AppState) -> a2kit.HealthResult:
    """Readiness probe for `_meta.health` / `a2web health`."""
    # SqliteResource is non-Optional; we verify the underlying connection
    # is open by calling _ensure (idempotent — fast path when already open).
    try:
        await state.sqlite._ensure()
    except Exception as exc:
        return a2kit.HealthResult.fail(f"sqlite open failed: {exc}")
    return a2kit.HealthResult.ok()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
