# a2kit v0.32.0 → v0.38.0 migration

## Why

a2kit shipped six releases (v0.33, v0.34-folded-into-v0.35, v0.35, v0.36, v0.37, v0.38) between 2026-05-13 and 2026-05-15. Three things move at once: (1) the round-7 + round-8 fixes we filed land in v0.35, (2) the DI surface is rebuilt as a standalone container with `Lazy[T]` + per-call scope + lazy first-use (v0.36 → v0.38), (3) lifecycle collapses to the async-CM protocol (v0.35).

The MCP transport unblock is the proximate reason — a2web v0.6.0 is down on every `mcp__a2web__fetch` call, validated by direct repro against the in-flight `2026-05-13-a2kit-v032-migration` archive. v0.35 fixes the dispatcher's `ctx`-binding bug we filed in round 8. POC against v0.38 confirms the fix survives the v0.36 DI rebuild (tool returns proper structured result, `notifications/message` carries LDD events, no TypeError).

A previous v0.35-only plan was drafted last session and immediately invalidated by the v0.36-38 cascade — see `superseded/` if you need the v0.35-shape reasoning. The v0.38 surface is markedly different on DI (lazy first-use replaced eager entry, `app.singleton` retired, topological order gone, `Lazy[T]` introduced) so going forward as v0.35 would have left value on the table.

| Impact | Shipped in | What a2web does |
|---|---|---|
| **Round 8 blocker — MCP `ctx`-binding** | v0.35 (folded v0.34) | Unblocks MCP transport completely; verified by repro |
| **Round 7 — `<app> health` pytest crash** | v0.33 | Fixed upstream; a2web health probe works on `uvx` installs |
| **Round 7 — `AmbientContextMissing.mode`** | v0.33 | Sharper errors; no a2web code change required |
| **Round 8 — MCP wire-error envelope** | v0.35 | Tool exceptions reach the wire as `ToolError({"class","message","traceback"})` instead of bare strings |
| **`@a2kit.read(idempotent=...)` removed** | v0.33 | Drop `idempotent=True` at `routers.py:22` |
| **`@a2kit.tool` / `name=` removed** | v0.33 | No a2web usage — clean |
| **`App(lifespan=cm)` removed** | v0.35 | Delete entire `@asynccontextmanager` lifespan; framework drives lifecycle via resource `__aenter__`/`__aexit__` |
| **`health_tool=True` becomes no-op** | v0.33 | Drop kwarg; `@app.health_check` auto-installs the tool |
| **`app.singleton(...)` removed** | v0.36 | Rename every site to `app.provide(...)` |
| **Eager entry replaced by lazy first-use** | v0.36 | Resources enter on first resolution from a tool call; no startup warm. Accept this — health probe still validates sqlite eagerly when called. |
| **`close()` / `aclose()` auto-detect removed** | v0.36 | Single-protocol convention — resources expose `__aenter__`/`__aexit__`. Keep existing `_ensure()` and `close()` methods as internal idempotent surfaces; new `__aenter__`/`__aexit__` are thin wrappers calling them. |
| **Topological order replaced by insertion order** | v0.36 | Register providers deps-first manually (Settings → Breakers → ProxyPool → Sqlite → Browser → Llm → AppState). LIFO unwind on exit. |
| **`Lazy[T]` for conditional injection** | v0.36 | Adopt for `LlmExtractorResource` (only enters when `ask=...` passed) and `BrowserPool` (only enters when a fetch escalates to browser tier). Real cold-start saving on the common path. |
| **`TestClient.call → .invoke`** | v0.35 | a2web tests don't use TestClient at the tool-boundary today — they call `orchestrate()` directly. Zero test changes required by this rename. |
| **TestClient returns marshaled dicts** | v0.35 | Same — current tests aren't affected; future integration tests must use dict access |
| **Tool exceptions wrap as `fastmcp.exceptions.ToolError`** | v0.35 | Same — no current test asserts cross-boundary exceptions |
| **Per-tool `timeout=` kwarg** | v0.35 | Not adopted in this migration; deferred to a sibling change |

Free wins inherited on the bump:
- v0.35 — `Router.tools` enforcement at App construction (validates our existing tuple)
- v0.35 — singleton `teardown=fn` (not needed once `__aexit__` is in place)
- v0.36 — `pydantic_settings.BaseSettings` auto-resolve (limited — see Decision 4 in design.md)

### v0.38 BaseSettings wire-detection limitation

`AppSettings` is a `BaseSettings` subclass. The v0.36 changelog claims "auto-resolves without explicit `provide()` registration". Verified by POC: this is **partial** — the container resolves BaseSettings transitively from factories, but `wire_input_params` doesn't recognize them, so declaring `settings: AppSettings` directly on a tool fails with FastMCP "Missing required keyword only argument". Workaround: explicit `app.provide(get_settings)` — same single-line registration we'd do anyway. Filed as round-10 feedback alongside this migration.

## What Changes

### `pyproject.toml`

- Bump `[tool.uv.sources] a2kit.tag` from `v0.32.0` to `v0.38.0`. Update spec: `a2kit>=0.32,<1` → `a2kit>=0.38,<1`.
- No new top-level deps required; v0.38 ships its own DI container in-tree.

### `src/a2web/state.py` — AppState slims to always-needed resources

- Drop `browser_pool: BrowserPool` and `llm_extractor: LlmExtractorResource` fields from AppState. They become independently-resolved Lazy resources accessed via tool/orchestrator signatures.
- Keep `settings`, `breakers`, `proxy_pool`, `sqlite` as concrete AppState fields — these are always needed on every fetch.
- `build_state` factory becomes: `def build_state(settings: AppSettings, breakers: AsyncCircuitBreakerFactory, proxy_pool: ProxyPool, sqlite: SqliteResource) -> AppState` — takes its deps via DI, returns the dataclass.
- Keep `@dataclass(slots=True)` — pure data bundle.

### `src/a2web/settings.py`

- No code change. `get_settings()` keeps its return annotation. Registered in `server.py` as a provider.

### `src/a2web/packages/http_cache.py` — SqliteResource gains protocol surface

- Add `async def __aenter__(self) -> SqliteResource: await self._ensure(); return self`.
- Add `async def __aexit__(self, *exc) -> None: await self.close()`.
- Existing `_ensure()` and `close()` methods remain untouched — internal idempotent surface used by lazy callers inside the class.

### `src/a2web/packages/browser_pool.py` — BrowserPool gains protocol surface

- Same `__aenter__`/`__aexit__` pattern around existing `_ensure()` / `close()`.

### `src/a2web/llm_resource.py` — LlmExtractorResource gains protocol surface

- Same `__aenter__`/`__aexit__` pattern around existing `_ensure()` / `close()`.

### `src/a2web/server.py` — imperative composition over `app.provide(...)`

- Drop `from contextlib import asynccontextmanager`.
- Delete the `@asynccontextmanager async def lifespan(app)` definition (lines 25-43).
- Construct App without `lifespan=` or `health_tool=`: `app = a2kit.App("a2web")`.
- Register providers in **dependency order**:
  ```python
  app.provide(get_settings)                # AppSettings
  app.provide(build_breakers)              # AsyncCircuitBreakerFactory
  app.provide(build_proxy_pool)            # ProxyPool          (needs settings)
  app.provide(SqliteResource)              # class-as-factory, no args
  app.provide(build_browser_pool)          # BrowserPool        (needs settings)
  app.provide(build_llm_extractor)         # LlmExtractorResource (needs settings, sqlite)
  app.provide(build_state)                 # AppState           (needs the 4 always-on resources)
  ```
- Factory functions live in this file (or `state.py`) as named functions — **no lambdas**.
- Keep `app.add_router(WebRouter())`, `app.ldd.events.register(_event_type)`, `app.ldd.add_sink(otel_sink)`, `@app.health_check` — all verified intact in v0.38.
- Keep `def main() -> None: a2kit.run(app)` unchanged — verified `a2kit.run` lifecycle wraps the new `async with app:` internally.

### `src/a2web/routers.py` — tool signature gains Lazy resources

- Drop `idempotent=True` from `@a2kit.read(...)` decorator (v0.33 break).
- `fetch` tool gains two new params:
  ```python
  browser_pool: Lazy[BrowserPool],
  llm_extractor: Lazy[LlmExtractorResource],
  ```
- Tool body threads them into `orchestrate(...)` as kwargs.
- Add `from a2kit.packages.di import Lazy` import.

### `src/a2web/fetcher.py` — orchestrator takes Lazy resources

- `orchestrate(url, *, state, browser_pool, llm_extractor, ...)` signature gains the two Lazy params.
- Inside orchestrator, the LLM extraction path (`_phase_extract` when `ask` is set) calls `await llm_extractor()` to resolve the resource. Without an `ask=` argument, `llm_extractor` is never awaited and the resource never enters.
- Inside the browser escalation path (`_escalate_browser`), call `await browser_pool()` once per escalation.
- Pass the resolved (non-Lazy) values down to phases via `FetchContext` or explicit kwargs — phases stay sync-of-resources at the point they're called.

### `src/a2web/handlers/` and `src/a2web/tiers/`

- Handlers/tiers that need `BrowserPool` or `LlmExtractorResource` get them via the orchestrator's already-resolved value passed through `FetchContext` — no DI wiring required. The Lazy unwrapping happens once at the orchestrator seam, not per-handler.

### `CLAUDE.md` — reflect the new DI shape

- Update the "Architecture" section: AppState carries the always-on resources (settings, breakers, proxy_pool, sqlite); browser_pool and llm_extractor are independently-provided Lazy resources surfaced at the tool seam.
- Update "Conventions": replace `app.singleton(AppState, build_state)` reference with `app.provide(...)` per-resource; note insertion-order requirement.
- Update "Never" list: drop "Never reintroduce a module-level `atexit` resource-close hook — use the App's `lifespan=` context manager `finally` block" (lifespan kwarg is gone). Replace with "Never bypass `__aenter__` for lazy init — register the resource with `app.provide(T)` and let the framework enter it on first resolution".

### `BACKLOG.md`

- Delete the "MCP transport broken in a2web v0.6.0, awaiting a2kit fix" entry (round-8 fix lands here).

### `docs/history/A2KIT_FEEDBACK_v0.33.md`, `A2KIT_FEEDBACK_v0.32-mcp.md`, `A2KIT_FEEDBACK.md`

- No changes in this migration. Round-7/8/9 asks were addressed by a2kit; archive the live `A2KIT_FEEDBACK.md` once the migration lands and start round 10 in a new live file (separate change, not this one).

## Out of scope (sibling change `a2web-mcp-feature-wave`)

- Reddit search URL handler (`/r/<sub>/search/?q=...` → `search.json`)
- LLM extras → core (bundle `anthropic` + `claude-agent-sdk` in base deps)
- Captcha pre-routing (Google/Bing search → DDG/Brave rewrite)
- `@a2kit.read(timeout="60s")` kwarg adoption
- TestClient-driven integration tests (would catch any future MCP-only regression like round 8)
