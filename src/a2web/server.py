"""a2web server entrypoint — composition on `fastmcp.FastMCP` directly.

a2kit is gone. What it used to own and where it went:

| a2kit                          | now                                     |
|--------------------------------|-----------------------------------------|
| `App` subclass + `routers`      | `build_mcp_server()` below              |
| `app.provide(...)` container    | `components.build_components()`         |
| implicit wire/injected split    | explicit tool signatures (`routers.py`) |
| `EncodingPlan` inference        | the literal table in `wire.py`          |
| `McpErrorRenderStage` + mw      | `error_wire.py`                         |
| resource `__aenter__` on resolve| `scope.ResourceScope`                   |

**Lifecycle is FastMCP's `lifespan=`.** Resources still enter lazily on first
use — `ResourceScope` records them as they are entered — and the lifespan's
exit unwinds the scope LIFO. Nothing is entered at boot, so cold start stays
cheap and a keyless deploy still serves `fetch_raw`.

**Middleware order is load-bearing.** `TypedErrorEnvelopeMiddleware` is added
first, so it is outermost and sees the `ToolError` that `guard_tool` raised;
`EnvelopeContentMiddleware` sits inside it and only ever touches success
results. Reversing them would let the envelope middleware try to re-encode an
error payload.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from plugin_surface import load_surface
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from . import log as a2web_log
from ._manifests.sinks import Sink
from .components import Components, build_components
from .error_wire import TypedErrorEnvelopeMiddleware
from .routers import register_cookies_tools, register_web_tools
from .settings import AppSettings, get_settings
from .wire import EnvelopeContentMiddleware

if TYPE_CHECKING:
    from .cache import SqliteResource

__all__ = ["build_google_provider", "build_mcp_server", "main", "serve_http_main"]


def _configure_logging(settings: AppSettings) -> None:
    """Install a2web's logging surface and the manifest sinks.

    `propagate=False` + a NullHandler floor is load-bearing, not tidiness: MCP
    is served over stdio, so a record escaping to the root logger's default
    stderr writer can interleave with the JSON-RPC stream.
    """
    a2web_log.configure(
        level=settings.log_level,
        enabled=settings.log_enabled,
        wire_level=settings.log_wire_level,
    )
    # Factories returning `Unavailable` (e.g. OTel with no SDK) are dropped
    # before reaching the logger. `add_handler` replaces same-type sinks —
    # the logger is process-wide and this function is not.
    for handler in load_surface("a2web._manifests.sinks", Sink, settings, logger=a2web_log.get_logger()).values():
        a2web_log.add_handler(handler)


def build_mcp_server(
    *,
    settings: AppSettings | None = None,
    components: Components | None = None,
    **fastmcp_kwargs: Any,
) -> FastMCP:
    """Build the production MCP server.

    `components` is the test seam that `app.provide(T, fake)` used to be —
    build one with overrides via `build_components(...)` and hand it in.
    """
    resolved = settings if settings is not None else get_settings()
    _configure_logging(resolved)
    parts = components if components is not None else build_components(settings=resolved)

    @asynccontextmanager
    async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await parts.aclose()

    fastmcp_kwargs.setdefault("lifespan", _lifespan)
    mcp = FastMCP(name="a2web", **fastmcp_kwargs)

    register_web_tools(mcp, parts)
    # The local-only cookies tool: a2web served as a network MCP server has no
    # local browser to mirror cookies from, so the tool is absent rather than
    # present-and-failing.
    if resolved.expose_cookies_tool:
        register_cookies_tools(mcp, parts)

    mcp.add_middleware(TypedErrorEnvelopeMiddleware())
    mcp.add_middleware(EnvelopeContentMiddleware())
    _register_health_route(mcp, parts)
    return mcp


async def check_sqlite(sqlite: SqliteResource) -> bool:
    """Readiness probe. Receiving an entered `sqlite` IS the assertion.

    Scope decision (deployable-container-ci §6.4): readiness asserts the
    SUBSTRATE only, NOT that an LLM backend is configured. `fetch_raw` serves
    with zero LLM config, so a keyless deploy is degraded-but-serving, not
    broken — and `query` already surfaces a loud per-request `llm_unavailable`
    operator hint (ADR-0009). Gating readiness on LLM config would make an
    orchestrator restart-loop a valid fetch-only container. Do not add an LLM
    assertion here.
    """
    return sqlite is not None


def _register_health_route(mcp: FastMCP, parts: Components) -> None:
    """Serve `GET /health` — the route the Dockerfile HEALTHCHECK curls.

    a2kit's multiplex parent served this for free, so the sunset's Phase 4
    silently 404'd it: the container kept serving MCP correctly while every
    30s probe failed, which after `--retries=3` marks the container unhealthy
    and invites an orchestrator restart-loop on a perfectly healthy process.
    Nothing in the test suite noticed, because the probe lived in the
    Dockerfile rather than in Python. It is restored here, next to the check
    it calls, so the two cannot drift apart again.

    Deliberately dumb, matching the old behaviour: it reports that the
    substrate opened, not that the service is useful. `check_sqlite` owns the
    scope reasoning — read it before adding an assertion here.
    """

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def _health(_request: Request) -> JSONResponse:
        try:
            sqlite = await parts.sqlite()
            ok = await check_sqlite(sqlite)
        except Exception as exc:
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
        if not ok:
            return JSONResponse({"status": "degraded"}, status_code=503)
        return JSONResponse({"status": "ok", "version": __version__})


def main() -> None:
    """stdio entrypoint. The Typer CLI is restored in sunset Phase 5."""
    build_mcp_server().run()


# --------------------------------------------------------------------- #
# Authenticated HTTP serve entrypoint
# --------------------------------------------------------------------- #


def build_google_provider(settings: AppSettings) -> object | None:
    """Construct the FastMCP Google OAuth provider from env, or None if unset.

    Gating:

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

    from .cache import cache_dir

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

    When unconfigured, the endpoint serves open — identical to the pre-auth
    container. Host/port come from `A2WEB_HTTP_HOST` / `A2WEB_HTTP_PORT`
    (defaults `0.0.0.0` / `8000`).
    """
    import os

    settings = get_settings()
    provider = build_google_provider(settings)
    mcp = build_mcp_server(settings=settings, auth=provider)
    mcp.run(
        transport="http",
        host=os.environ.get("A2WEB_HTTP_HOST", "0.0.0.0"),  # noqa: S104 - container binds all interfaces by design
        port=int(os.environ.get("A2WEB_HTTP_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
