# v0.5 step 1 — a2kit v0.26.0 → v0.27.2 migration

## Why

a2kit shipped 0.26.1 (additive) + 0.27.0 (breaking) on 2026-05-11. Together they deliver every gap a2web filed in feedback round 4 (`docs/history/A2KIT_FEEDBACK_v0.26.md`):

| Round-4 gap | Shipped in | Adapter code a2web deletes |
|---|---|---|
| Typed-emit honors `register(T)` | 0.26.1 | `_event_payload` + `_emit` shim (~30 LOC, `fetcher.py`) |
| Lifecycle hook DI like `@health_check` | 0.27.0 breaking | container ceremony in `@on_startup`/`@on_shutdown` (~14 LOC, `server.py`) |
| Async singleton factories | 0.27.0 — solved oppositely: **Resource pattern with lock-in-resource**, factories stay sync | `Optional` fields on `AppState` + standalone locks + `ensure_*` helpers (~50 LOC, `state.py`) |
| `App.container()` non-Optional + drop `connection=None` | 0.27.0 breaking | None-guards + dead surface (~8 LOC, `server.py`) |
| `ToolContext.null()` for unit tests | 0.26.1 — `a2kit.testing.null_context()` | `ctx: ToolContext \| None` propagation through 6 phase functions + ~12 None-guards |
| `Param("desc")` positional shorthand | 0.26.1 | cosmetic, ~5 LOC at `routers.py` |

That's **~120 LOC of pure adapter shim** the migration deletes automatically. v0.27.0 is breaking — delaying it accumulates surface drift against an obsolete shape, and PR5 (lazy state) from the simplification plan becomes redundant with the Resource pattern.

The Resource pattern (a2kit's README §"Resource pattern (lazy-init)") is the canonical answer to "resources that need an event loop." Each resource owns its own `asyncio.Lock` and a `_ensure()` method; AppState holds resources as non-Optional fields. Better than the lifespan-yield factory shape I originally proposed.

This is Stage 1 of the broader simplification plan. Subsequent stages — `packages/` structural split, logging/proxy swaps, fetcher decomposition — ride on the cleaner foundation this migration provides.

## What Changes

### `pyproject.toml`

- Bump `a2kit` pin: `tag = "v0.26.0"` → `tag = "v0.27.2"`.

### `src/a2web/state.py`

- `AppState` becomes ~30 LOC with **non-Optional** resource fields. Today's 136 LOC drops by ~75%.
- Delete:
  - `sqlite: aiosqlite.Connection | None`
  - `browser_pool: BrowserPool | None`
  - `browser_lock: asyncio.Lock | None`
  - `llm_extractor: Extractor | None`
  - `llm_lock: asyncio.Lock | None`
  - `llm_unavailable_reason: str | None`
  - `ensure_browser_pool()` helper function
  - `ensure_llm_extractor()` helper function
- Replace with:
  - `sqlite: SqliteResource` (new — wraps aiosqlite, owns its lock, lazy-opens on first call)
  - `browser_pool: BrowserPool` (existing class adopts Resource pattern — lock moves inside)
  - `llm_extractor: LlmExtractorResource` (new — wraps current `Extractor`, owns lazy-init + unavailable-reason tracking)
- `build_state()` stays sync (a2kit 0.27 hard requirement).

### `src/a2web/server.py`

- `@app.on_startup` signature: `async def _open_resources(_app: a2kit.App)` → `async def _open_resources(state: AppState)`. DI is automatic.
- Body: delete the `container = _app.container(); if container is None: raise; state = await container.resolve(...)` ceremony. The startup hook becomes a fail-fast warm-up: `await state.sqlite._ensure()` (so config errors surface at startup, not first request).
- Same for `@app.on_shutdown` — DI-resolves `state: AppState`, body becomes `await state.sqlite.close(); await state.browser_pool.close()`.
- `@app.health_check` unchanged (already DI-aware).

### `src/a2web/fetcher.py`

- **Delete `_emit()` and `_event_payload()`** (~30 LOC). All `await _emit(ctx, TierStarted(...))` calls become `await a2kit.ldd.event(ctx, TierStarted(...))` (a2kit 0.26.1 typed-emit auto-derives name from class + flattens via dataclasses.asdict).
- **`ctx: a2kit.ToolContext | None` → `ctx: a2kit.ToolContext`** in every phase function signature (`_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`, `_escalate_browser`, `_phase_cache_write`, `_dispatch_archive`, `_phase_extract_answer`).
- Delete every `if ctx is None: return` guard inside emit calls (~12 sites).
- Top-level `fetch()` keeps `ctx: a2kit.ToolContext` (already non-Optional via router signature).

### `src/a2web/routers.py`

- `Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")]` → `Annotated[str, a2kit.Param("Absolute http(s) URL to fetch.")]` (positional shorthand) for the single-line description on `url`. The two multi-line descriptions stay as-is (kwarg form is clearer when the string is multi-line).
- No other changes.

### Tests

- Any unit test that calls phase functions directly with `ctx=None` switches to `from a2kit.testing import null_context; ctx = null_context()`.
- `bootstrap_state_for_test` (if present) — verify it constructs the new Resource-pattern state correctly. Likely just `build_state()` works as-is since the factory is sync.
- E2E tests via `a2kit.testing.client(app)` unchanged.

### Docs

- `CLAUDE.md` — update Architecture section: AppState fields are non-Optional; locks live inside resources; Resource pattern is the canonical shape.
- `BACKLOG.md` — strike "lazy state cleanup (PR5)"; it's delivered by this migration.

## Out of Scope

Explicitly NOT touching in this migration:
- Logging swap (structlog + RotatingFileHandler) — separate PR.
- Proxy → purgatory — separate PR.
- `packages/` folder structural split — separate PR.
- Fetcher decomposition (`_phase_tier_loop` breakdown, escalation merge) — separate Plan, depends on this migration.
- Events module collapse (whether `events/types.py` survives) — depends on fetcher decomposition.
- PR1 micro-cleanups (`Rendered.from_dict`, `*_hint` accumulator, etc.) — separate PR, can land in parallel.

This PR is **one focused thing**: bring a2web onto a2kit v0.27.2 with no adapter shims left.

## Risks

| Risk | Mitigation |
|---|---|
| Resource pattern interaction with `aiosqlite.Connection` quirks (open-twice, cancellation mid-`_ensure`) | a2kit's example shows the pattern with sqlite explicitly; `_lock` + double-check is canonical. Add a stress test for concurrent first-call. |
| LLM extractor's "unavailable reason" tracking — currently a state field, needs to move into the resource class | `LlmExtractorResource.unavailable_reason: str \| None` property. Same shape, just lives inside. Verified by existing tests on `ask=`-bearing fetches. |
| Test fixtures that bypass `a2kit.testing.client` and construct `AppState` directly may break | Audit pass on test files; replace direct AppState construction with `build_state()` calls. |
| Camoufox optional-dep handling — first browser dispatch can still raise `ImportError` | Handle inside `BrowserPool._ensure()`, return clean error to `BrowserTier.fetch()`. Same surface contract as today, internalized. |
| Coverage drop during migration | Run `make check` after each commit in the task list. Coverage gate stays ≥85%. |

## Success Criteria

- `make check` passes (lint + ty + test, coverage ≥85%).
- `make dev` MCP server starts and serves `fetch` successfully against 3 real URLs (reddit, arxiv, github).
- `fetcher.py` no longer contains `_emit` or `_event_payload` functions.
- `state.py` is ≤50 LOC, zero `Optional` fields on `AppState`.
- `server.py` lifecycle hooks contain zero `container.resolve(...)` calls.
- a2web's `docs/history/A2KIT_FEEDBACK_v0.26.md` round-4 items can all be checked off.
- Net diff: ~-100 to -150 LOC across `state.py` + `server.py` + `fetcher.py`, partially offset by new Resource classes (~+50 LOC). Expected net: **~-100 LOC**.
