# Tasks — a2kit v0.27.2 migration

Execute top-to-bottom. Each section ends with a commit boundary; `make check` must pass before moving on.

## 1. Bump dependency

- [ ] Update `pyproject.toml`: `a2kit` pin from `tag = "v0.26.0"` to `tag = "v0.27.2"`.
- [ ] `uv sync --all-extras`.
- [ ] Confirm install: `uv pip show a2kit | grep Version` → `0.27.2`.
- [ ] **Do NOT run tests yet** — the migration is breaking, expect failures.

## 2. Build the three Resource classes (additive, no removal yet)

- [ ] Create `src/a2web/cache/sqlite_resource.py` — `SqliteResource` class wrapping existing `open_sqlite_with_schema` + `cache_get` + `cache_put`. Add `_ensure` / `close` with internal `asyncio.Lock` per the README pattern.
- [ ] Create `src/a2web/llm/resource.py` — `LlmExtractorResource` class wrapping today's `ensure_llm_extractor` logic. Owns `_extractor`, `_unavailable_reason`, internal `_lock`. Returns `None` (not raises) on permanent unavailability.
- [ ] Update `src/a2web/browser/pool.py` — rename `BrowserPool.start()` to `BrowserPool._ensure()`. Make idempotent under existing `self._lock` with double-checked open. Add `_lock` to `__init__` if not already there.
- [ ] Add unit tests for each Resource: double-check concurrent `_ensure()`, idempotent `close()`, `_ensure()` after `close()` re-opens.
- [ ] `make lint` passes. (Tests may still fail at app level — that's fine; the resources themselves test in isolation.)

**Commit:** "v0.5 step 1a: add SqliteResource / LlmExtractorResource / BrowserPool._ensure (additive)"

## 3. Migrate `state.py` to non-Optional resources

- [ ] Replace `AppState` field declarations:
  - Remove `sqlite: aiosqlite.Connection | None`, replace with `sqlite: SqliteResource`.
  - Remove `browser_pool: BrowserPool | None` + `browser_lock`, replace with `browser_pool: BrowserPool` (non-Optional, constructed in factory).
  - Remove `llm_extractor: Extractor | None` + `llm_lock` + `llm_unavailable_reason`, replace with `llm_extractor: LlmExtractorResource`.
- [ ] Update `build_state(settings)` to construct each resource: `SqliteResource(settings)`, `BrowserPool(...)`, `LlmExtractorResource(settings)`. **Factory stays sync** (a2kit 0.27 enforces this).
- [ ] Delete `ensure_browser_pool()` and `ensure_llm_extractor()` free functions.
- [ ] Run `make lint` — many callers will still reference removed symbols. Expected; fix in next step.

**Commit:** Defer commit until step 4 lands (callers will be red).

## 4. Update all call sites to use Resource methods

- [ ] `src/a2web/fetcher.py`:
  - Replace `state.sqlite is not None` checks with calls to `state.sqlite.get(...)` directly. Cache-miss returns `None`; cache disabled is a method-level concern, not state-level. (Decision: pass `bypass=True` flag in or have a `state.sqlite.disabled` property — pick one in implementation.)
  - Replace `await cache_get(state.sqlite, url, hash)` → `await state.sqlite.get(url, hash)`.
  - Replace `await cache_put(state.sqlite, ...)` → `await state.sqlite.put(...)`.
  - Replace `ensure_browser_pool(state)` calls → just use `state.browser_pool` directly; `acquire()` calls `_ensure()` internally.
  - Replace `ensure_llm_extractor(state)` → just use `state.llm_extractor` directly; `extract()` calls `_ensure()` internally and returns `None` on unavailability.
- [ ] `src/a2web/tiers/browser.py`:
  - Calls `state.browser_pool.acquire(url)` directly. Catch `ImportError` from `_ensure()` propagating up, translate to operator hint as today.
- [ ] `src/a2web/cache/sqlite_cache.py`: keep file for now (compute_profile_hash, is_live_only, cache_dir helpers stay). Remove `cache_get`, `cache_put`, `open_sqlite_with_schema` — these become methods on `SqliteResource`. Or: import the methods through and re-export for backwards compat. **Decision: delete the free functions; update all call sites.**
- [ ] Audit tests for direct construction of `AppState`: tests that pass `sqlite=conn` must construct `SqliteResource` instead. Likely 3-5 test files.
- [ ] `make lint` passes.

**Commit:** "v0.5 step 1b: state.py + call sites adopt Resource pattern"

## 5. Migrate `server.py` lifecycle hooks to DI

- [ ] Change `@app.on_startup` signature: `async def _open_resources(_app: a2kit.App)` → `async def _open_resources(state: AppState)`.
- [ ] Body: replace the entire container ceremony with `await state.sqlite._ensure()` (fail-fast warm-up).
- [ ] Same for `@app.on_shutdown`: signature → `(state: AppState)`. Body → `await state.sqlite.close(); await state.browser_pool.close(); await state.llm_extractor.close()`.
- [ ] `@app.health_check` already DI-aware; verify unchanged.
- [ ] `make check` passes at this point — application runs.

**Commit:** "v0.5 step 1c: lifecycle hooks use DI-aware signatures"

## 6. Delete typed-emit adapter shim

- [ ] `src/a2web/fetcher.py`:
  - Delete `_emit()` function.
  - Delete `_event_payload()` function.
  - Replace every `await _emit(ctx, EventType(...))` call with `await a2kit.ldd.event(ctx, EventType(...))`. Confirm a2kit handles `Verdict` enum serialization automatically (it does per 0.26.1 changelog).
- [ ] Run E2E test (`make dev` + manual fetch) to confirm typed events emit correctly on the wire with the same payload shape.
- [ ] `make check` passes.

**Commit:** "v0.5 step 1d: drop _emit / _event_payload adapter (a2kit 0.26.1 typed-emit)"

## 7. Migrate `ToolContext | None` → `ToolContext` everywhere

- [ ] Update phase function signatures in `src/a2web/fetcher.py`:
  - `_phase_tier_loop` — `ctx: a2kit.ToolContext` (non-Optional)
  - `_phase_extract` — same
  - `_phase_gate_and_escalate` — same
  - `_escalate_browser` — same
  - `_phase_cache_write` — same
  - `_dispatch_archive` — same
  - `_phase_extract_answer` — same
  - `_run_pipeline` — same
  - Top-level `fetch()` — `ctx: a2kit.ToolContext` (was already non-None at router boundary)
- [ ] Delete every `if ctx is None: return` / `if ctx is not None:` guard inside emit calls. Grep: `grep -n "ctx is None" src/a2web/fetcher.py` should return 0 hits.
- [ ] Update tests: any direct phase call with `ctx=None` switches to `from a2kit.testing import null_context; ctx=null_context()`.
- [ ] `make check` passes.

**Commit:** "v0.5 step 1e: ToolContext non-Optional in phase functions (null_context for tests)"

## 8. Adopt `Param("desc")` positional shorthand (cosmetic)

- [ ] `src/a2web/routers.py`: change `a2kit.Param(description="Absolute http(s) URL to fetch.")` → `a2kit.Param("Absolute http(s) URL to fetch.")` for the single-line case on the `url` parameter.
- [ ] Leave multi-line descriptions on `include_links`, `debug`, `ask` in kwarg form (clearer for multi-line strings).
- [ ] `make check` passes.

**Commit:** "v0.5 step 1f: Param positional shorthand for one-line descriptions"

## 9. Documentation + final cleanup

- [ ] Update `CLAUDE.md` Architecture section:
  - Replace "browser pool stays Optional because they need an event loop" with "all resources are non-Optional; each owns its `_ensure()` + lock per Resource pattern."
  - Update the `AppState` description to match the new shape.
  - Strike any mention of `ensure_browser_pool`, `ensure_llm_extractor`, `browser_lock`, `llm_lock`.
- [ ] Update `BACKLOG.md`: strike "PR5 — lazy state cleanup" (delivered by this migration).
- [ ] Update `docs/history/A2KIT_FEEDBACK_v0.26.md`: add a short "Migration outcome" footer noting all six items shipped + a2web migrated successfully.
- [ ] Update `CHANGELOG.md`: add the v0.5-step-1 entry.

**Commit:** "v0.5 step 1g: docs catch up to Resource pattern"

## 10. Validation gate

- [ ] `make check` — all green (lint + ty + test, coverage ≥85%).
- [ ] `make dev` — server starts cleanly.
- [ ] Manual E2E: `uv run a2web web fetch --url=https://news.ycombinator.com/item?id=1` succeeds.
- [ ] Manual E2E: `uv run a2web web fetch --url=https://arxiv.org/abs/2401.00001` succeeds.
- [ ] Manual E2E: `uv run a2web web fetch --url=https://github.com/yoselabs/a2kit --ask='What is the latest version?'` succeeds (or returns operator hint if `[llm]` not installed).
- [ ] Grep absence: `grep -rn "_emit\|_event_payload\|ensure_browser_pool\|ensure_llm_extractor\|browser_lock\|llm_lock\|llm_unavailable_reason\|ToolContext | None\|connection=None\|_app: a2kit" src/a2web/` returns 0 hits.
- [ ] Net diff measurement: `git diff --stat main...` should show ~-100 LOC net.

If all green: ready to merge.
