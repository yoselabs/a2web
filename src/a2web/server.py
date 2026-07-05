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

Heavy/conditional resources (BrowserBackend, LlmExtractorResource) are surfaced
at the tool seam as `Lazy[T]` (see `routers.py`) so the cold-start cost is
paid only when the fetch path actually needs them.

Logging is stdlib logging: typed events emit via
`await a2kit.log.info(payload)`; sinks are `logging.Handler`s attached via
`app.log.add_handler(...)`.
"""

from __future__ import annotations

import a2kit
from a2kit.config import A2kitConfig, McpConfig

from ._manifests.sinks import Sink
from ._plugin import load_surface
from .cookie_jar import build_cookie_jar
from .packages.http_cache import SqliteResource
from .packages.llm_extract import Provider
from .routers import CookiesRouter, WebRouter
from .settings import get_settings
from .state import (
    RobustBrowserBackend,
    build_breakers,
    build_browser_backend,
    build_browser_robust_backend,
    build_llm_extractor,
    build_proxy_pool,
    build_selected_provider,
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

    # a2web opts out of a2kit's `code_mode=True` default (shipped as a config
    # knob in a2kit 0.46 — see docs/history/A2KIT_FEEDBACK_v0.44.md). a2web is a
    # few-tool, lean-payload server: `ask`/`fetch_raw`/`refresh` already distill
    # content server-side, so the code-execution sandbox (search/get_schema/
    # execute) is pure tax on the ~95% single-`ask` path. With it off, the MCP
    # surface advertises the named tools directly (the bare-name pins in
    # routers.py go live). Env still wins: `A2KIT_MCP__CODE_MODE=true` re-enables
    # the sandbox per-deployment (ADR 0022 inverted source order).
    config = A2kitConfig(mcp=McpConfig(code_mode=False))


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
    app.provide(build_browser_backend)  # BrowserBackend — fast browser rung (patchright); Lazy at tool seam
    # robust rung (zendriver) — distinct DI key; Lazy, enters only on the 2nd browser dispatch
    app.provide(RobustBrowserBackend, build_browser_robust_backend)
    app.provide(Provider, build_selected_provider)  # best LLM provider (Protocol key); raises ResourceUnavailable when none
    app.provide(build_llm_extractor)  # LlmExtractorResource — needs settings + sqlite + Lazy[Provider] (Lazy at tool seam)
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
    # Scope decision (deployable-container-ci §6.4): readiness asserts the
    # SUBSTRATE only, NOT that an LLM backend is configured. `fetch_raw` serves
    # with zero LLM config, so a keyless deploy is degraded-but-serving, not
    # broken — and `ask` already surfaces a loud per-request `llm_unavailable`
    # operator hint (ADR-0009). Gating readiness on LLM config would make an
    # orchestrator restart-loop a valid fetch-only container. Liveness
    # (`GET /health`) stays dumber still. Do not add an LLM assertion here.
    _ = sqlite
    return a2kit.HealthResult.ok()


app = build_app()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
