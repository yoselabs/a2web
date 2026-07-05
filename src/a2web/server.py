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
from .settings import AppSettings, get_settings
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


class _A2WebServer(A2Web):
    """Server-safe variant: the local-only `cookies_refresh` tool is NOT exposed.

    a2web served as a network MCP server has no local browser to mirror cookies
    from, so `CookiesRouter` is dropped from the surface. `build_app` selects
    this class unless `settings.expose_cookies_tool` is set (local serve). Name +
    config are inherited; only `routers` narrows.
    """

    routers = (WebRouter,)


def _app_class_for(settings: AppSettings) -> type[A2Web]:
    """Pick the App class from the cookies-exposure toggle. Pure — no I/O — so the
    router-gating decision is unit-testable without the settings cache."""
    return A2Web if settings.expose_cookies_tool else _A2WebServer


def build_app() -> A2Web:
    """Build a fresh a2web `A2Web` instance.

    Tests build a fresh app per test and pass fakes via `.provide(T, fake)`
    last-write-wins, then enter `make_client(build_app_for_test(...))`.
    """
    app = _app_class_for(get_settings())()

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


# --------------------------------------------------------------------- #
# Authenticated HTTP serve entrypoint (a2kit `docs/patterns/mcp-auth.md`)
# --------------------------------------------------------------------- #


def build_google_provider(settings: AppSettings) -> object | None:
    """Construct the FastMCP Google OAuth provider from env, or None if unset.

    a2kit is auth-agnostic on the MCP surface by design (ADR 0010) — the OAuth
    provider is a FastMCP object handed to `serve_process(mcp_options={"auth": …})`,
    not an `a2kit.packages.auth` AuthSpec. Gating:

    - No `GOOGLE_CLIENT_ID` → `None` (endpoint stays open; ship behind Tailscale/LAN).
    - `GOOGLE_CLIENT_ID` set but `GOOGLE_CLIENT_SECRET`/`GOOGLE_BASE_URL` missing →
      loud `ValueError` at boot (never silently serve open on a half-config).
    - All three set → a `GoogleProvider` with a persistent FileTreeStore token
      store (survives restarts; optionally Fernet-encrypted at rest).
    """
    if not settings.google_client_id:
        return None
    missing = [
        name
        for name, value in (
            ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
            ("GOOGLE_BASE_URL", settings.google_base_url),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Google OAuth is partially configured: GOOGLE_CLIENT_ID is set but "
            f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing. "
            "Set all of GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_BASE_URL, "
            "or unset GOOGLE_CLIENT_ID to serve without auth."
        )

    from fastmcp.server.auth.providers.google import GoogleProvider
    from key_value.aio.stores.filetree import FileTreeStore

    from .packages.http_cache import cache_dir

    store_dir = settings.oauth_cache_dir or str(cache_dir() / "oauth")
    token_store: object = FileTreeStore(data_directory=store_dir)
    if settings.oauth_encryption_key:
        from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

        # Fixed salt: the secret is `oauth_encryption_key`; the salt only needs to
        # be STABLE across restarts so the derived key reproduces (else the stored
        # tokens can't be decrypted after a restart).
        token_store = FernetEncryptionWrapper(
            key_value=token_store,
            source_material=settings.oauth_encryption_key,
            salt="a2web-oauth-token-store",
        )

    return GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        base_url=settings.google_base_url,
        required_scopes=settings.google_required_scopes or None,
        jwt_signing_key=settings.google_jwt_signing_key or None,
        client_storage=token_store,
    )


def serve_http_main() -> None:
    """Container entrypoint: serve MCP over HTTP, config-gated Google OAuth.

    This is the programmatic serve path a2kit's MCP-auth recipe prescribes — the
    bare `a2web serve` CLI cannot express a provider object. Builds the runtime,
    narrows to the MCP surface, and injects the provider (when configured) via
    `serve_process(mcp_options={"auth": provider})`. When unconfigured, the
    endpoint serves open — identical to the pre-auth container. Host/port come
    from `A2WEB_HTTP_HOST` / `A2WEB_HTTP_PORT` (defaults `0.0.0.0` / `8000`).
    """
    import os

    from a2kit.packages.serve import serve_process
    from a2kit.runtime import apply_selection, build

    settings = get_settings()
    provider = build_google_provider(settings)
    runtime = apply_selection(build(app), ["surface=mcp"])
    mcp_options = {"auth": provider} if provider is not None else None
    serve_process(
        runtime,
        transport="http",
        host=os.environ.get("A2WEB_HTTP_HOST", "0.0.0.0"),  # noqa: S104 - container binds all interfaces by design
        port=int(os.environ.get("A2WEB_HTTP_PORT", "8000")),
        internal_uds=None,
        mcp_options=mcp_options,
    )


if __name__ == "__main__":
    main()
