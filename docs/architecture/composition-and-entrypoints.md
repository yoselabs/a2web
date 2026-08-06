# Composition and entrypoints

Covers `src/a2web/settings.py`, `server.py`, `cli.py`, `components.py`, and the
shelf `async-scope` primitives — the boot path from process start to a
registered MCP server or CLI, and the ONE place the object graph is built.

## a2kit → FastMCP direct (retired 2026-07-22)

a2web composes on `fastmcp.FastMCP` directly. a2kit was retired by
`openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/`; its
App/Router/DI-container/formatter spine is replaced by ~300 lines a2web owns.
What moved where:

| a2kit | now |
|---|---|
| `App` subclass + `routers` ClassVar | `server.build_mcp_server()` |
| `app.provide(...)` container | `components.build_components()` — the ONE composition root |
| implicit wire/injected param split | explicit tool signatures in `routers.py` (design D1) |
| `Lazy[T]` from the container | shelf `async_scope.Lazy` + `memoized(factory)` |
| resource entry on resolution | shelf `async_scope.ResourceScope` (LIFO, records only after a successful `__aenter__`) |
| `EncodingPlan` inference + `FormatRoutingMiddleware` | `wire.py` — a LITERAL `_TSV_FIELDS` table, not inference |
| `McpErrorRenderStage` + envelope middleware | `error_wire.py` |
| `a2kit.log` | `a2web.log` (Phase 1) |
| `encode_tsv` | shelf `lean-wire` (adopted 2026-07-22; `_tsv_compat.py`<!-- gone --> is gone) |
| `a2kit.testing.client` | `tests/_helpers/mcp.py` |
| `a2kit lint rego` | **dropped — a real loss**, see bd issue a2web-526 |

`a2effect` (the typed error taxonomy + `ErrorEnvelope`) is now a DIRECT
dependency rather than transitive through a2kit.

Read `openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/design.md`
before touching composition, wire encoding, or the error envelope. Migration
history predating the sunset lives in `openspec/changes/archive/`; the last two
are `2026-06-19-a2kit-v044-migration/` (clean pin bump, touched nothing a2web
consumed) and `2026-06-11-a2kit-v043-migration/` (where the surface actually
moved — ADR-0028 unified surface, ADR-0027 LDD refound).

**Two guarantees hand-wiring turned from structural into convention**, each now
pinned by an architecture test: cold-start laziness
(`tests/architecture/test_cold_start_laziness.py` — a cache- or raw-served
`query` must resolve neither the browser nor the LLM thunk) and
single-composition-root (`tests/architecture/test_one_composition_root.py`).

## Module notes

- `src/a2web/settings.py` — `AppSettings(BaseSettings)` from env (`A2WEB_*`) + optional YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, `jina_key` (env-only secret). `${ENV_VAR}` references inside YAML resolve at load time.
- `src/a2web/server.py` — `build_mcp_server(*, settings=None, components=None, **fastmcp_kwargs) -> FastMCP`. Builds the graph via `build_components()`, registers the tools, installs two middlewares and a lifespan whose exit calls `components.aclose()` (LIFO teardown of whatever was actually entered). **Middleware order is load-bearing**: `TypedErrorEnvelopeMiddleware` is added FIRST so it is outermost and sees the `ToolError` that `guard_tool` raised; `EnvelopeContentMiddleware` sits inside it and only touches success results. `expose_cookies_tool` gates whether `register_cookies_tools` runs — it defaults to `False`, so on a served a2web the tool is ABSENT rather than present-and-failing. (The gate is that setting plus the dropped `[cookies]` extra. It is NOT "the container has no browser" — the published image does have one; see the Deployment section of `CLAUDE.md`.) `serve_http_main()` is the container entrypoint: `build_mcp_server(auth=provider)` + `mcp.run(transport="http")`, with config-gated Google OAuth. Also registers `GET /health` (`_register_health_route`) — the route the Dockerfile HEALTHCHECK curls; a2kit's multiplex parent served it for free, Phase 4 404'd it for a day, and `tests/capabilities/endpoint_auth/test_health_route.py` reads the path out of the Dockerfile so the two cannot drift again.
- `src/a2web/cli.py` — the Typer CLI, **derived** from the registered MCP tools rather than hand-written in parallel. `build_cli(components=…)` walks `mcp.list_tools()`, and each tool's `inspect.signature` becomes the command's options via `field_to_typer_annotation` (vendored from a2kit's 54-line `_field_to_typer.py`), so `--help` text and the MCP `inputSchema` descriptions are the same string and cannot disagree. Safe only because D1 made the parameter list wire-only; under a2kit's ambient wire/injected split the derivation would have been a guess. `_TOOL_GROUPS` is a LITERAL tool→(group, command) table for the same reason `wire._TSV_FIELDS` is literal — a tool missing from it is a build-time error, not a silently absent command. Commands own their teardown (`components.aclose()` in a `finally`): skipping it does not merely leak, the aiosqlite worker thread keeps the process alive after the JSON prints. Dropped vs a2kit: `--format`, `--json` (a no-op), `schema`/`list-tools`/`code`/`_meta`, and the never-called 50k truncate cap.
- `src/a2web/components.py` — **the one composition root.** `Components` is a frozen dataclass holding `settings` + `scope` + six `Lazy[T]` thunks (`state`, `sqlite`, `browser_backend`, `browser_robust_backend`, `llm_extractor`, `cookie_jar`). `build_components(*, settings=None, **factory_overrides)` wires them; nothing is constructed or entered until something awaits a thunk. The `*_factory` overrides are the test seam that `app.provide(T, fake)` used to be — `dataclasses.replace` fails loudly on a field that does not exist, so an override that stopped matching the graph breaks the test instead of quietly disarming it.
- shelf `async-scope` — `ResourceScope` (enter + LIFO unwind; records ONLY after a successful `__aenter__`, keeps unwinding past a failing `__aexit__`) + `memoized(factory) -> Lazy[T]` (double-checked lock, so twenty concurrent cold `query` calls launch one browser, not twenty) + the `Lazy[T]` alias. **Promoted out of a2web 2026-08-02** (was `scope.py`<!-- gone --> + `lazy.py`<!-- gone -->, themselves what survived a2kit's 599-line DI container); a2web keeps `components.py`'s six-thunk graph, which is the domain half. The cold-start guarantee is a property of `memoized`, so `test_cold_start_laziness.py` now pins an adopted primitive — deliberately: the guarantee is generic, the graph is not.
