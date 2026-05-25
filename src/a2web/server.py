"""a2web server entrypoint — `a2kit.App` composition (v0.38 surface).

Imperative composition: each long-lived resource is registered as its own
provider via `app.provide(...)`. The container resolves them in deps-first
order on first use (lazy first-use, a2kit v0.36+); LIFO unwind on shutdown.

No `lifespan=` kwarg, no `@asynccontextmanager` lifespan body — resources
own their own lifecycle via `__aenter__`/`__aexit__` (thin wrappers around
each resource's idempotent `_ensure` / `close` methods, kept as the
internal lazy-call surface).

Heavy/conditional resources (BrowserPool, LlmExtractorResource) are surfaced
at the tool seam as `Lazy[T]` (see `routers.py`) so the cold-start cost is
paid only when the fetch path actually needs them.
"""

from __future__ import annotations

import a2kit
import a2kit.ldd

from .cookie_jar import build_cookie_jar
from .events import otel_sink
from .events.types import (
    CookiesAttached,
    CookiesStale,
    StageEnded,
    StageStarted,
    TierEnded,
    TierHeartbeat,
    TierStarted,
)
from .packages.http_cache import SqliteResource
from .routers import CookiesRouter, WebRouter
from .settings import get_settings
from .state import (
    build_breakers,
    build_browser_pool,
    build_llm_extractor,
    build_proxy_pool,
    build_state,
)

# ----------------------------------------------------------------------- #
# App composition — providers registered in dependency order (v0.36 uses
# insertion order, not topological). Each downstream factory depends only
# on already-registered types.
# ----------------------------------------------------------------------- #


app = a2kit.App("a2web")

# Order matters: deps before dependents.
app.provide(get_settings)  # AppSettings (BaseSettings) — explicit per design.md decision 4
app.provide(build_breakers)  # AsyncCircuitBreakerFactory — no deps
app.provide(build_proxy_pool)  # ProxyPool — needs settings
app.provide(SqliteResource)  # class-as-factory — no required ctor args
app.provide(build_browser_pool)  # BrowserPool — needs settings (Lazy at tool seam)
app.provide(build_llm_extractor)  # LlmExtractorResource — needs settings + sqlite (Lazy at tool seam)
app.provide(build_cookie_jar)  # CookieJarResource — needs settings + sqlite (Lazy at tool seam)
app.provide(build_state)  # AppState — bundles the four always-on resources

app.add_router(WebRouter())
app.add_router(CookiesRouter())

# Register typed event payloads so a2kit can route them through the typed-emit
# path (one call emits dump → event → progress).
for _event_type in (TierStarted, TierEnded, StageStarted, StageEnded, TierHeartbeat, CookiesAttached, CookiesStale):
    app.ldd.events.register(_event_type)

# OTel sink runs sequentially after the wire emit, best-effort under
# cancellation (a2kit logs exceptions to a2kit.ldd.sinks).
app.ldd.add_sink(otel_sink)


@app.health_check
async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
    """Readiness probe for `_meta.health` / `a2web health`.

    Per a2kit v0.39 `OPERATIONAL_CONTRACTS` Q-HealthChecks: kwarg resolution
    enters the resource (`__aenter__`) before this body runs. Receiving
    `sqlite` here means the connection opened. Open-time failures crash the
    probe loudly during resolution — that's correct for a catastrophic
    sqlite-open failure, not a "degraded" check.
    """
    _ = sqlite
    return a2kit.HealthResult.ok()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
