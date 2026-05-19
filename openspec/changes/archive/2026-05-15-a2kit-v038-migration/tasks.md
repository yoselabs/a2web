# Tasks — a2kit v0.32 → v0.38 migration

Step ordering is load-bearing — see `design.md` "Migration order recap". Don't reorder without thinking about why.

---

## Step 0 — Verification spike + pin bump

- [ ] 0a. **Final API surface verification against v0.38** (in case anything shifted since the POC session):
  - `app.provide(fn)` accepts a function with return annotation — no lambdas (framework rejects with `TypeError: requires a return annotation`).
  - `app.provide(SomeClass)` accepts class-as-factory when `__init__` is no-arg.
  - `app.has_provider(T)` exists.
  - `a2kit.packages.di.Lazy` exists and is importable.
  - `app.ldd.events.register`, `app.ldd.add_sink`, `app.ldd.sinks` exist.
  - `a2kit.run(app)` signature unchanged.
  - Container resolves `Lazy[T]` params correctly when factory deps include them.
  Record any divergence in `design.md` "Decisions".

- [ ] 0b. In `pyproject.toml`: bump `[tool.uv.sources] a2kit.tag` from `v0.32.0` to `v0.38.0`. Update spec: `a2kit>=0.32,<1` → `a2kit>=0.38,<1`.

- [ ] 0c. `uv sync --all-extras`. Confirm install clean.

- [ ] 0d. Run `make check`. Capture the failure surface as the migration's red baseline. Expected:
  - `TypeError` from `@a2kit.read(idempotent=True)` at module import.
  - `TypeError` from `App(..., lifespan=lifespan)` at `server.py:46`.
  - `AttributeError` from `app.singleton(...)` (removed in v0.36).
  - Tests fail with import errors cascading from the above.

---

## Step 1 — Forced-error site fixes (mechanical)

- [ ] 1a. `routers.py:22` — drop `idempotent=True` from `@a2kit.read(...)`. The remaining kwargs `open_world=True` and `title="Fetch Web Page"` stay. (`@read` is spec-idempotent.)

- [ ] 1b. `server.py:14` — drop `from contextlib import asynccontextmanager` import.

- [ ] 1c. `server.py:25-43` — delete the entire `@asynccontextmanager async def lifespan(app)` block. The sqlite warm and LIFO close logic moves into resource `__aenter__`/`__aexit__` (Step 2).

- [ ] 1d. `server.py:46` — rewrite App construction: `app = a2kit.App("a2web")`. Drop `health_tool=True` (no-op in v0.33+) and `lifespan=lifespan` (removed in v0.35).

- [ ] 1e. `make check`. Lifespan/decorator errors should clear; `app.singleton` errors remain for Step 4.

---

## Step 2 — Resource `__aenter__` / `__aexit__` wrappers (purely additive)

For each resource class, add the CM protocol pair as thin wrappers around existing `_ensure()` / `close()`. Internal `_ensure()` / `close()` methods stay UNCHANGED.

- [ ] 2a. `src/a2web/packages/http_cache.py` — `SqliteResource`:
  ```python
  async def __aenter__(self) -> "SqliteResource":
      await self._ensure()
      return self

  async def __aexit__(self, exc_type, exc, tb) -> None:
      await self.close()
  ```

- [ ] 2b. `src/a2web/packages/browser_pool.py` — `BrowserPool`: same shape.

- [ ] 2c. `src/a2web/llm_resource.py` — `LlmExtractorResource`: same shape.

- [ ] 2d. `ProxyPool` (`src/a2web/packages/proxy_routing.py`) and `AsyncCircuitBreakerFactory` (third-party `purgatory`): no `__aenter__`/`__aexit__` required — framework gracefully skips non-CM singletons.

- [ ] 2e. `make check`. No new failures expected — pure additions.

---

## Step 3 — AppState slim

- [ ] 3a. `src/a2web/state.py` — `AppState` dataclass:
  - Drop `browser_pool: BrowserPool` field.
  - Drop `llm_extractor: LlmExtractorResource` field.
  - Keep `settings`, `breakers`, `proxy_pool`, `sqlite`.
  - Update class docstring to reflect "always-on resources" semantic.

- [ ] 3b. `src/a2web/state.py` — `build_state` factory:
  - Old signature: `def build_state(settings: AppSettings | None = None) -> AppState`.
  - New signature: `def build_state(settings: AppSettings, breakers: AsyncCircuitBreakerFactory, proxy_pool: ProxyPool, sqlite: SqliteResource) -> AppState`.
  - Body: `return AppState(settings=settings, breakers=breakers, proxy_pool=proxy_pool, sqlite=sqlite)`.
  - Container chain-resolves the four deps automatically (each is a separate provider registered in Step 4).

- [ ] 3c. `tests/test_app_state.py` — update direct AppState constructions to match the new four-field shape.

---

## Step 4 — Provider registration in `server.py` (deps-first order)

Replace the single `app.singleton(AppState, build_state)` (or equivalent) with seven providers, registered in **insertion order = dependency order**. All factories are **named functions** — no lambdas.

- [ ] 4a. Add factory functions (in `server.py` or a new `factories.py` module — pick whichever keeps `server.py` under 100 lines):
  ```python
  def build_breakers() -> AsyncCircuitBreakerFactory:
      return AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)

  def build_proxy_pool(settings: AppSettings) -> ProxyPool:
      return ProxyPool(routes=settings.routes, proxies=settings.proxies)

  def build_browser_pool(settings: AppSettings) -> BrowserPool:
      return BrowserPool(
          max_pool=settings.browser_max_pool,
          idle_timeout_s=settings.browser_idle_timeout_s,
          page_budget_s=settings.browser_page_budget_s,
      )

  def build_llm_extractor(settings: AppSettings, sqlite: SqliteResource) -> LlmExtractorResource:
      return LlmExtractorResource(settings, sqlite)
  ```

- [ ] 4b. `server.py` — replace any existing singleton/provide block with this exact registration sequence (order matters):
  ```python
  app.provide(get_settings)                # AppSettings
  app.provide(build_breakers)              # AsyncCircuitBreakerFactory (no deps)
  app.provide(build_proxy_pool)            # ProxyPool (needs settings)
  app.provide(SqliteResource)              # class-as-factory, no args
  app.provide(build_browser_pool)          # BrowserPool (needs settings)
  app.provide(build_llm_extractor)         # LlmExtractor (needs settings, sqlite)
  app.provide(build_state)                 # AppState (needs the 4 always-on resources)
  ```

- [ ] 4c. Keep `app.add_router(WebRouter())`, the `app.ldd.events.register(...)` loop, `app.ldd.add_sink(otel_sink)`, the `@app.health_check` decorator, and `main()` → `a2kit.run(app)` UNCHANGED.

- [ ] 4d. `make check`. Expected new failures only in `routers.py` (no `Lazy[T]` yet) — Step 5.

---

## Step 5 — Lazy resource adoption at the tool / orchestrator seam

- [ ] 5a. `src/a2web/routers.py` — add import: `from a2kit.packages.di import Lazy`.

- [ ] 5b. `src/a2web/routers.py` — `WebRouter.fetch` signature gains two params (place them after `state: AppState`):
  ```python
  browser_pool: Lazy[BrowserPool],
  llm_extractor: Lazy[LlmExtractorResource],
  ```

- [ ] 5c. `src/a2web/routers.py` — tool body passes them into `orchestrate(...)`:
  ```python
  return await orchestrate(
      url,
      state=state,
      browser_pool=browser_pool,
      llm_extractor=llm_extractor,
      ...,
  )
  ```

- [ ] 5d. `src/a2web/fetcher.py` — `orchestrate` (or the `fetch` entry function) signature gains the two Lazy kwargs. Update type imports: `from a2kit.packages.di import Lazy`.

- [ ] 5e. `src/a2web/fetcher.py` — at the LLM-extraction site (`_phase_extract` when `ask` is set):
  - Before: reach into `state.llm_extractor` to get the resource.
  - After: at the orchestrator level, `await llm_extractor()` once when entering the extract-with-ask branch. Thread the resolved value into the phase via `FetchContext` or as an explicit kwarg to `_phase_extract`. Never call `await llm_extractor()` when `ask` is None.

- [ ] 5f. `src/a2web/fetcher.py` — at the browser escalation site (`_escalate_browser`):
  - Before: reach into `state.browser_pool`.
  - After: `await browser_pool()` once at the top of the escalation path. Pass the resolved `BrowserPool` instance into the browser tier via FetchContext or as a kwarg.

- [ ] 5g. `src/a2web/fetcher.py` — confirm phases that don't need browser/llm don't touch the Lazy callables. Phases stay resource-agnostic at the Lazy boundary — they receive concrete resources from the orchestrator.

- [ ] 5h. `make check`. Should green now. If `make check` fails on type-checking the FetchContext or kwargs, ensure the resolved (non-Lazy) types flow downstream — Lazy unwrap is once-per-call at the orchestrator seam, not propagated through.

---

## Step 6 — Docs alignment

- [ ] 6a. `CLAUDE.md` — Architecture section:
  - Update the AppState bullet: now carries always-on resources (settings, breakers, proxy_pool, sqlite). Browser pool and LLM extractor are independently-provided Lazy resources surfaced at the tool seam.
  - Update server.py bullet: imperative `app.provide(...)` per resource in deps-first order. No more `lifespan=` kwarg.
  - Update routers.py bullet: tool signature includes `browser_pool: Lazy[BrowserPool]` and `llm_extractor: Lazy[LlmExtractorResource]`.

- [ ] 6b. `CLAUDE.md` — Conventions section:
  - Replace `app.singleton(...)` references with `app.provide(...)`.
  - Add: "Register providers in deps-first order — v0.36+ uses insertion order, not topological."
  - Add: "Heavy/conditional resources use `Lazy[T]` at the tool seam — keeps cold start cheap on the common path."

- [ ] 6c. `CLAUDE.md` — Never list:
  - Remove: "Never reintroduce a module-level `atexit` resource-close hook — use the App's `lifespan=` context manager `finally` block."
  - Add: "Never wire lifecycle in `server.py`'s body — register the resource with `app.provide(T)` and let `__aenter__`/`__aexit__` handle it."
  - Add: "Never declare `settings: AppSettings` as a direct tool param without explicit `app.provide(get_settings)` — v0.38 BaseSettings auto-resolve is wire-side incomplete (see design.md Decision 4)."

- [ ] 6d. `BACKLOG.md` — delete the entry "MCP transport broken in a2web v0.6.0, awaiting a2kit fix".

- [ ] 6e. `CHANGELOG.md` — add v0.7.0 entry under "Unreleased":
  - Migration to a2kit v0.38.
  - MCP transport unblocked (round-8 fix).
  - DI re-architected: each resource is its own provider.
  - `Lazy[BrowserPool]` / `Lazy[LlmExtractorResource]` for cold-start savings.
  - Behavior change: resources enter lazily on first fetch, not at startup. Sqlite errors now surface as structured `ToolError` on first call instead of crashing at boot.

---

## Step 7 — Full verification

- [ ] 7a. `make check` green (lint + ty + tests, coverage ≥85%).

- [ ] 7b. `make dev` boots the MCP server cleanly. No errors in startup banner.

- [ ] 7c. MCP stdio repro — `printf '{"jsonrpc":"2.0",...tools/call name=fetch arguments={"url":"https://example.com/"}}' | a2web serve` returns a structured `FetchResponse` (not a bare error string). Save the response to `/tmp/v038_mcp_check.json` for the PR description.

- [ ] 7d. MCP wire LDD events — confirm `notifications/message` lines appear with `a2kit_kind: "event"` for `TierStarted` / `TierEnded` payloads during a real fetch. Save sample to `/tmp/v038_mcp_events.json` for the PR description.

- [ ] 7e. `a2web health` (via `uvx --from . a2web health`) returns OK — verifies sqlite warm via the health-check path, plus the v0.33 pytest-import fix.

- [ ] 7f. `a2web web fetch --url=https://example.com/` (CLI path) — confirms no CLI regressions and the Lazy resources gate correctly (no browser/llm warm on a happy-path fetch).

- [ ] 7g. `a2web web fetch --url=https://example.com/ --ask="what's on this page?"` — only this call should trigger `LlmExtractorResource.__aenter__`. Confirm via debug logs or instrumentation.

---

## Step 8 — Archive prep

- [ ] 8a. Move this change to `openspec/changes/archive/2026-05-15-a2kit-v038-migration/`.

- [ ] 8b. Update `docs/history/A2KIT_FEEDBACK.md` (round 7, still in flight) — strike through any items addressed by v0.33/v0.35. If all items are addressed, rotate the file to `A2KIT_FEEDBACK_v0.33.md` per existing convention.

- [ ] 8c. File round 10 feedback as a separate change: BaseSettings wire-detection gap (Decision 4 in design.md) + any v0.38 observations from the migration.
