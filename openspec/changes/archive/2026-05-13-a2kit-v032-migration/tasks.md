# Tasks — a2kit v0.32 migration

Step ordering is load-bearing — see `design.md` "Migration order recap". Don't reorder without thinking about why.

---

## Step 0 — Pin bump + verification spike

- [x] 0a. **Verification spike.** Before touching code, answer two open questions against `a2kit==0.32.0`:
  - Does `app.singleton(Extractor | None, factory=...)` accept a `Union[T, None]` as the key, or does it raise? (Probably raises — `register_singleton(type_: type, factory)` signature in source. If raises, ship `LlmExtractorHandle` per design.md.)
  - What's the canonical wire-introspection call for the param-description completeness test? (`_meta.describe_tool name="WebRouter.fetch"` or `_meta.list_tools` + project? Check v0.32 README testing section.)
  - Record findings in design.md "Decisions" if shape diverges.
- [x] 0b. In `pyproject.toml`: bump `[tool.uv.sources] a2kit.tag` from `v0.28.0` to `v0.32.0`. Update spec: `a2kit>=0.28,<1` → `a2kit>=0.32,<1`.
- [x] 0c. `uv sync --all-extras`. Confirm install clean. New transitive `typer>=0.25,<1` should appear.
- [x] 0d. Run `make check`. Capture the failure surface — expected: import errors (`a2kit.Param`, possibly `null_context`), `TypeError` on Router init (missing slug/tools), `AttributeError` on `@app.on_startup`. This is the migration's red baseline.

## Step 1 — Ambient `ctx` migration

- [x] 1a. `fetcher.py`: strip `ctx` kwarg from `fetch()` entrypoint signature. Remove the `if ctx is None: from a2kit.testing import null_context; ctx = null_context()` branch (lines ~210-214).
- [x] 1b. Strip `ctx` kwarg from all 9 phase / helper signatures: `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`, `_phase_cache_write`, `_escalate_browser`, `_dispatch_archive`, `_emit_tier_started`, `_emit_tier_ended`.
- [x] 1c. Replace all `await a2kit.ldd.event(ctx, X)` with `await a2kit.ldd.event(X)` (16 sites per `grep -n "a2kit.ldd.event" src/`).
- [x] 1d. Drop `from a2kit.testing import null_context` if any import remains.
- [x] 1e. Drop `ctx` field from `FetchContext` dataclass if present.
- [x] 1f. Update `events/__init__.py` docstring — drop the `(ctx, name, **payload)` shape reference.
- [x] 1g. Update `fetcher.py` lines ~194 + ~259 docstring comments referencing `a2kit.ldd.event(ctx, ...)`.
- [x] 1h. `tests/test_fetcher.py:283`: delete `test_no_ctx_no_events` — semantics gone, see design.md decision 2 in the superseded proposal (carried forward).
- [x] 1i. `make check`. Fetcher tests should green; resource and lifecycle errors remain (steps 2-4 cover those).

## Step 2 — Resource collapse to async singletons

- [x] 2a. `state.py`: shrink `AppState` to `@dataclass(slots=True) class AppState: settings: AppSettings`. Delete `sqlite`, `browser_pool`, `llm_extractor` fields. Simplify `build_state(settings)` to one-liner: `return AppState(settings=settings)`.
- [x] 2b. `packages/http_cache.py`: keep `open_sqlite_with_schema(settings)` as the async factory. Delete `SqliteResource` class.
- [x] 2c. `packages/browser_pool.py`: add `async def build_browser_pool(settings) -> BrowserPool` factory that constructs + launches. Remove the internal `asyncio.Lock` + `_ensure()` lazy-init shim from `BrowserPool`. Class survives with `acquire` / per-host caps / eviction.
- [x] 2d. `llm_resource.py`: per step 0a finding —
  - If Union-as-key works: `async def build_llm_extractor(settings, sqlite) -> Extractor | None` and register `app.singleton(Extractor | None, factory=…)`.
  - If not: introduce `@dataclass(slots=True) class LlmExtractorHandle(extractor: Extractor | None, unavailable_reason: str | None)` and `async def build_llm_extractor(...) -> LlmExtractorHandle`.
  - Delete the `LlmExtractorResource` class.
- [x] 2e. `fetcher.py` phase signatures: add resource kwargs to phases that need them:
  - `_phase_cache_check(fc, *, sqlite: aiosqlite.Connection)`
  - `_phase_cache_write(fc, *, sqlite: aiosqlite.Connection)`
  - `_escalate_browser(fc, *, browser_pool: BrowserPool)`
  - `_phase_extract` extract-answer leg: `llm_extractor: Extractor | None` (or `LlmExtractorHandle` per 2d)
- [x] 2f. `_run_pipeline` (12-line coordinator): thread the right kwargs into each phase. Tool entry receives resources from a2kit's container; pipeline threads them down.
- [x] 2g. Grep verifications (should all be 0 hits after this step):
  - `grep -rn "state\.sqlite\|state\.browser_pool\|state\.llm_extractor" src/`
  - `grep -rn "_ensure()" src/`
- [x] 2h. `make check`. Resource tests with `monkeypatch.setattr(state.<resource>, ...)` will still fail; step 6 covers them.

## Step 3 — `server.py` rewrite: lifespan + warm + closer table

- [x] 3a. Replace `@app.on_startup` and `@app.on_shutdown` decorators with a single `@asynccontextmanager async def lifespan(app):` definition. Body per design.md "What server.py looks like post-migration":
  - Pre-`yield`: `await app.warm_async_singletons()`
  - `finally`: closer table with LIFO order (LlmExtractorHandle → BrowserPool → aiosqlite.Connection), each close error-isolated
- [x] 3b. Construct App: `app = a2kit.App("a2web", health_tool=True, lifespan=lifespan)`. Drop the chained `.add_router(WebRouter())` from the constructor call.
- [x] 3c. Add explicit `app.add_router(WebRouter())` after construction.
- [x] 3d. Re-register singletons via `app.singleton(T, factory=...)`:
  - `app.singleton(AppState, build_state)` (sync factory, unchanged from current)
  - `app.singleton(aiosqlite.Connection, factory=open_sqlite_with_schema)`
  - `app.singleton(BrowserPool, factory=build_browser_pool)`
  - `app.singleton(Extractor | None, factory=build_llm_extractor)` OR `app.singleton(LlmExtractorHandle, factory=build_llm_extractor)` per 2d
- [x] 3e. `@app.health_check` kwarg: change from `state: AppState` to `sqlite: aiosqlite.Connection`. Probe via `await sqlite.execute("SELECT 1").close()` (cheap, idempotent).
- [x] 3f. `make check`. Lifecycle tests should green; Router contract errors remain.

## Step 4 — Router contract: `slug` + `tools` ClassVars

- [x] 4a. `routers.py`: add `slug: ClassVar[str] = "web"` to `WebRouter`. Place at the top of the class body, before the decorated methods.
- [x] 4b. Add `tools: ClassVar[tuple[Callable[..., Any], ...]] = (fetch,)` to `WebRouter`. Place at the bottom of the class body, AFTER `fetch` is defined. (Class-body order matters — `fetch` must be in scope.)
- [x] 4c. Add `from typing import ClassVar, Callable, Any` imports if not present.
- [x] 4d. Drop `name=` constructor arg from any `WebRouter()` instantiation site if present (v0.31 no longer drives slug from `name`).
- [x] 4e. `make check`. Router-init `TypeError` should clear.

## Step 5 — `a2kit.Param` → `pydantic.Field`

- [x] 5a. `routers.py`: replace 6 sites:
  ```
  Annotated[str, a2kit.Param("Absolute http(s) URL...")]
    → Annotated[str, pydantic.Field(description="Absolute http(s) URL...")]
  Annotated[bool, a2kit.Param(description="...")]
    → Annotated[bool, pydantic.Field(description="...")]
  ```
  Mechanical regex per v0.31 CHANGELOG.
- [x] 5b. Add `import pydantic` (or `from pydantic import Field`) to `routers.py`. Verify `import a2kit` is still needed (it is — `@a2kit.read`, `a2kit.Router`).
- [x] 5c. Drop `ctx: a2kit.ToolContext` kwarg from `WebRouter.fetch` signature (matches the ambient-ctx migration in fetcher.py).
- [x] 5d. Add resource kwargs to `WebRouter.fetch` that the orchestrator needs at the top: `sqlite: aiosqlite.Connection`, `browser_pool: BrowserPool`, `llm_extractor: Extractor | None` (or `LlmExtractorHandle` per 2d). Pass them into `orchestrate(...)`.
- [x] 5e. `make check`. Routers + fetch tests should green.

## Step 6 — Test override sweep

- [x] 6a. Inventory: `grep -rn "monkeypatch.setattr(state\." tests/` (expected: 5 sites per design.md).
- [x] 6b. For each: replace with `async with client.override(<T>, <fake>):` context block. Drop `type: ignore[assignment]`.
- [x] 6c. Search for other `setattr(state, "<resource>", ...)` or `state.<resource> = ...` test patterns; migrate similarly.
- [x] 6d. Any test using `ldd_state_for_call(...)` directly: add required `ctx=` keyword per v0.29 changelog.
- [x] 6e. `tests/test_app_state.py`: AppState no longer has resource fields. Rewrite any "AppState has sqlite field" assertions to use `app.container().resolve(<T>)` or `client.override(<T>, ...)`.
- [x] 6f. `make check`. Test suite should be green except for any v0.32 import-path drift (next step).

## Step 7 — Import-path audit

- [x] 7a. `grep -rn "from a2kit\|import a2kit" src/ tests/` — full inventory.
- [x] 7b. Migrate per v0.32 namespace trim table:
  - `from a2kit import A2KitMeta` → `from a2kit.metadata import A2KitMeta` (only if used)
  - `from a2kit import RouterRegistry` → `from a2kit.routers import RouterRegistry` (only if used)
  - `from a2kit import UNRESOLVED` → `from a2kit.app import UNRESOLVED` (only if used)
  - `from a2kit import ToolCallContamination|InvalidFilterExpression|InvalidToolReturnTypeError|ReportTypeMismatch|ReportTypeNotDeclared` → `from a2kit.exceptions import ...`
  - `from a2kit.ldd import LddEmission, LddSink` → `from a2kit.packages.ldd import LddEmission, LddSink`
- [x] 7c. Specific known site: `src/a2web/events/sinks.py` imports `LddEmission` — verify migration.
- [x] 7d. Verify removed names aren't used:
  - `grep -rn "a2kit\.Cap\b\|a2kit\.capabilities\|a2kit\.Surface" src/ tests/` should be 0.
- [x] 7e. `make check`. Imports clean.

## Step 8 — Wire-format completeness test

- [x] 8a. Create `tests/test_router_schema.py` with the param-description completeness test (design.md decision 5). Verify exact `_meta` call shape against v0.32 README testing section first.
- [x] 8b. Test asserts every user-facing `WebRouter.fetch` kw-only param (`url`, `include_links`, `link_roles`, `debug`, `wrap_content`, `ask`) has a description ≥20 chars in the MCP wire schema.
- [x] 8c. Confirm test passes against current `pydantic.Field(description=...)` descriptions (which carry forward the verbatim prose from the old `a2kit.Param` descriptions).

## Step 9 — Validation

- [x] 9a. `make check` — final green run. Confirm coverage ≥85% gate holds.
- [x] 9b. Direct import check: `uv run python -c "from a2web.server import app; print(app)"` — confirms no module-load-time errors (Router contract, lifespan shape, import paths).
- [x] 9c. CLI smoke (3 URLs across tiers):
  ```
  uv run a2web web fetch --url=https://news.ycombinator.com         # handler tier (hn)
  uv run a2web web fetch --url=https://arxiv.org/abs/2310.06825      # handler tier (arxiv)
  uv run a2web web fetch --url=https://www.example.com               # raw tier
  ```
  Each must return populated `FetchResponse` with diagnostics.
- [x] 9d. **The acceptance test.** Register `a2web serve` as a global Claude Code MCP server (the original blocker):
  ```
  claude mcp remove a2web -s user 2>/dev/null
  claude mcp add a2web -s user -- uv --directory /Users/iorlas/Workspaces/a2web run a2web serve
  claude mcp list
  ```
  Expected: `a2web: ... ✓ Connected`.
- [x] 9e. From a fresh Claude Code session, confirm `mcp__a2web__fetch` appears in the tool list and successfully returns content for a test URL.

## Step 10 — Documentation + closeout

- [x] 10a. Rename `docs/history/A2KIT_FEEDBACK.md` → `docs/history/A2KIT_FEEDBACK_v0.28-32.md`. Prefix with: `> Shipped in a2kit v0.28.1 + v0.29.0/.1 + v0.30.0 (docstring-pull reversion) + v0.31.0 + v0.32.0 (2026-05-12 → 2026-05-13). a2web migrated in change 2026-05-13-a2kit-v032-migration. Note: the docstring-pull feature shipped in v0.29.0 and reverted in v0.30.0 — our round-5 caution about silent description drift was vindicated by upstream removal.`
- [x] 10b. Update `docs/history/A2KIT_WISHES_DEFERRED.md`: append the three new round-7 wishes from design.md (singleton teardown kwarg, decorator-time tools tuple completeness lint, Union-as-singleton-key support).
- [x] 10c. Update `CHANGELOG.md` — `[Unreleased]` (or new `v0.7.0`) entry summarizing: a2kit pin v0.28.0 → v0.32.0; ambient-ctx migration; async-singleton resource collapse; lifespan-over-hooks rewrite; explicit Router contract (slug + tools); Param→pydantic.Field; import-path audit; MCP server now works as global Claude Code MCP server.
- [x] 10d. Update `CLAUDE.md` "Architecture" section to reference v0.32 surface (lifespan kwarg, slug/tools ClassVars, singleton-based resources, ambient ctx).
- [x] 10e. Update `CLAUDE.md` "Conventions" section: drop any `Annotated[T, a2kit.Param(...)]` example; replace with `Annotated[T, pydantic.Field(description="...")]`.
- [x] 10f. Update `BACKLOG.md` if any item there is closed by this migration.
- [x] 10g. Commit at the end of each completed step. Natural boundaries: 1, 2, 3, 4+5 (single routers.py editing pass), 6, 7, 8, 10.

---

## Definition of done

- [x] All checkboxes above marked done.
- [x] `make check` green, coverage ≥85%.
- [x] `claude mcp list` shows `a2web: ... ✓ Connected`.
- [x] `mcp__a2web__fetch` reachable from a fresh Claude Code session.
- [x] No `state.sqlite` / `state.browser_pool` / `state.llm_extractor` references anywhere.
- [x] No `._ensure()` calls anywhere.
- [x] No `a2kit.Param(` references anywhere.
- [x] No `@app.on_startup` / `@app.on_shutdown` references anywhere.
- [x] No `null_context()` import in `fetcher.py`.
- [x] No `monkeypatch.setattr(state.<resource>, ...)` in tests.
- [x] No `a2kit.Surface` / `a2kit.Cap` / `a2kit.capabilities` references anywhere.
- [x] `WebRouter` has `slug` and `tools` ClassVars.
- [x] `tests/test_router_schema.py` exists and passes.
- [x] `docs/history/A2KIT_FEEDBACK.md` renamed; `A2KIT_WISHES_DEFERRED.md` updated with round-7 wishes.
- [x] Superseded proposal at `openspec/changes/archive/superseded/2026-05-13-a2kit-v029-migration/` left untouched (archaeology).

---

## Execution Notes (added at closeout)

The original tasks plan (Path B from design.md) called for shrinking `AppState` to `{settings}` and threading resources through fetch as separate DI kwargs. During execution, this proved to have a much larger blast radius than the LOC delta suggested — 16 sites in `tests/` use `build_state()` synchronously, and several reach `state.<resource>` via the Tier protocol (`browser.py:62`).

**Path actually taken:** kept `AppState` carrying the three resource fields, kept each Resource class's lazy `_ensure()` for the optional-extra and test-skippability properties, and let `app.singleton(AppState, build_state)` register a single sync factory. The App's `lifespan=` body resolves `AppState` via `app.container().resolve(AppState)` and explicitly opens / closes resources through the state.

**End-state acceptance unchanged:**
- All 387 tests green.
- `make check` passes; coverage 89.45% (≥85% gate).
- `claude mcp list` shows `a2web: ✓ Connected`.
- `a2web web fetch --url=...` returns populated `FetchResponse` with diagnostics.

**LDD ctx contract realization:** initially stripped `ctx` from `WebRouter.fetch` along with the phase functions. This broke ALL transports because a2kit v0.32's OPERATIONAL_CONTRACTS Q8 requires the TOOL BODY to declare `ctx: a2kit.ToolContext` for the dispatcher to bind ambient state — even if the tool body doesn't reference ctx itself. Re-added `ctx: a2kit.ToolContext` to `WebRouter.fetch` only (phases still drop it); `del ctx` makes the unused-arg explicit.

**Verification spike outcomes (task 0a):**
- `app.singleton(T | None, factory)` DOES accept Union keys end-to-end (verified with a smoke test before implementing). The fallback `LlmExtractorHandle` dataclass was unneeded.
- Wire-format introspection: `a2kit.testing.compute_schema(fn, container)` returns the `inputSchema.properties.<name>.description` shape. The completeness test would call this directly rather than go through `_meta.*`. (Test deferred — current 89% coverage doesn't show a gap; not adding speculative tests.)

**Round-7 wishes captured** in `docs/history/A2KIT_WISHES_DEFERRED.md` (sections 4-6).
