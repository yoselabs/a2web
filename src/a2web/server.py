"""a2web server entrypoint — `a2kit.App` composition (v0.43 surface).

ADR-0028 (unified surface): the App is authored by **subclassing** —
`A2Web` sets `name` + a `routers` ClassVar (a tuple of Router *classes*).
Each long-lived resource is registered imperatively via `app.provide(...)`
in `build_app()`; the container resolves them in deps-first order on first
use (lazy first-use), LIFO unwind on shutdown.

No `lifespan=` kwarg, no `@asynccontextmanager` lifespan body — resources
own their own lifecycle via `__aenter__`/`__aexit__` (thin wrappers around
each resource's idempotent `_ensure` / `close` methods, kept as the
internal lazy-call surface).

Heavy/conditional resources (BrowserPool, LlmExtractorResource) are surfaced
at the tool seam as `Lazy[T]` (see `routers.py`) so the cold-start cost is
paid only when the fetch path actually needs them.

Logging is stdlib logging: typed events emit via
`await a2kit.log.info(payload)`; sinks are `logging.Handler`s attached via
`app.log.add_handler(...)`.
"""

from __future__ import annotations

import a2kit

from ._manifests.sinks import Sink
from ._plugin import load_surface
from .cookie_jar import build_cookie_jar
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
# App composition — providers registered in dependency order (insertion
# order, not topological). Each downstream factory depends only on
# already-registered types.
# ----------------------------------------------------------------------- #


class A2Web(a2kit.App):
    """The a2web App (ADR-0028 subclass form).

    `routers` names Router *classes* (reference-composition); a2kit
    instantiates them at construction. Verbs auto-collect from the
    `@a2kit.read`/`@a2kit.write` markers — no `tools` ClassVar.
    """

    name = "a2web"
    routers = (WebRouter, CookiesRouter)


def build_app() -> A2Web:
    """Build a fresh a2web `A2Web` instance.

    Tests build a fresh app per test and pass fakes via `.provide(T, fake)`
    last-write-wins, then enter `make_client(build_app_for_test(...))`.
    """
    app = A2Web()

    # Order matters: deps before dependents.
    app.provide(get_settings)  # AppSettings (BaseSettings) — explicit per design.md decision 4
    app.provide(build_breakers)  # AsyncCircuitBreakerFactory — no deps
    app.provide(build_proxy_pool)  # ProxyPool — needs settings
    app.provide(SqliteResource)  # class-as-factory — no required ctor args
    app.provide(build_browser_pool)  # BrowserPool — needs settings (Lazy at tool seam)
    app.provide(build_llm_extractor)  # LlmExtractorResource — needs settings + sqlite (Lazy at tool seam)
    app.provide(build_cookie_jar)  # CookieJarResource — needs settings + sqlite (Lazy at tool seam)
    app.provide(build_state)  # AppState — bundles the four always-on resources

    # Log sinks come from the plugin manifest registry as `logging.Handler`s.
    # Handlers whose factories return Unavailable (e.g. OTel without the SDK
    # installed) are dropped before reaching the logger. They attach to the
    # `a2kit` logger and drain the typed-event LogRecords best-effort.
    for _handler in load_surface("a2web._manifests.sinks", Sink, get_settings()).values():
        app.log.add_handler(_handler)

    app.health_check(_check_sqlite)
    return app


async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
    """Readiness probe for `_meta.health` / `a2web health`.

    Per a2kit `OPERATIONAL_CONTRACTS` Q-HealthChecks: kwarg resolution
    enters the resource (`__aenter__`) before this body runs. Receiving
    `sqlite` here means the connection opened. Open-time failures crash the
    probe loudly during resolution — that's correct for a catastrophic
    sqlite-open failure, not a "degraded" check.
    """
    _ = sqlite
    return a2kit.HealthResult.ok()


app = build_app()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
