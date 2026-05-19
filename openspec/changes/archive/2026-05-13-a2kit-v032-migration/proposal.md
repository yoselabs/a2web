# a2kit v0.28.0 → v0.32.0 migration

## Why

a2kit shipped a 4-release wave (v0.28.1, v0.29.0, v0.29.1, v0.30.0, v0.31.0, v0.32.0) between 2026-05-12 and 2026-05-13. The wave fixes the FastMCP 3.x compatibility break that's currently blocking `a2web serve` as a global Claude Code MCP server, closes every open ergonomic gap from a2web feedback rounds 5 + 6, and reshapes the surface in three breaking ways (Param removal, lifespan-over-hooks, explicit Router contract).

A previous proposal targeting v0.29.1 was drafted and immediately invalidated by the same-day v0.30-32 cascade. See `openspec/changes/archive/superseded/2026-05-13-a2kit-v029-migration/SUPERSEDED.md`.

| Impact | Shipped in | What a2web does |
|---|---|---|
| **Round 6 blocker — FastMCP 3 break** (`tool.disable()` removed) | v0.28.1 | Unblocks `a2web serve` as global Claude Code MCP server |
| **Round 5 gap 1** — async resource boilerplate | v0.29.0 `app.singleton(T, async_factory)` | Collapse `SqliteResource` + `LlmExtractorResource` to factory fns; trim `BrowserPool` internals |
| **Round 5 gap 2** — `ctx` threading | v0.29.0 LDD primitives drop `ctx` (ambient via ContextVar) | Strip `ctx` kwarg from 9 phase fns + 16 `ldd.event` call sites |
| **Round 5 gap 3** — test resource override | v0.29.0 `TestClient.override(T, fake)` | Replace 5 `monkeypatch.setattr(state.…)` sites |
| **Round 5 gap 4** — `Annotated[Param]` verbosity | v0.29.0 docstring pull, v0.30.0 **REVERTED** | No-op — feature was reverted within 24h. Keep Annotated. |
| **Round 6 friction 1** — `_meta` namespace undocumented | v0.28.1 OPERATIONAL_CONTRACTS Q7 | Documentation only |
| **Round 6 friction 2** — wire payload inspection | v0.29.0 `TestClient.call_wire(tool, **kw)` | Enables a new param-description completeness test |
| **`a2kit.Param` removed** | v0.31.0 | 6 sites in `routers.py`: `a2kit.Param(...)` → `pydantic.Field(description=...)` |
| **Lifespan over lifecycle hooks** | v0.31.0 — `@on_startup/@on_shutdown` removed; `App(lifespan=…)` is the contract | Rewrite `server.py` lifecycle: lifespan async-context-manager + `app.warm_async_singletons()` + explicit cleanup in `finally` |
| **Explicit Router surface** | v0.31.0 — `slug` + `tools` ClassVars required | Add `slug = "web"` and `tools = (fetch,)` to `WebRouter`. `Router.install` and auto-bridged `on_startup` are gone (a2web doesn't use them). |
| **Top-level `a2kit.*` namespace trim** (22 → 10) | v0.32.0 | Audit imports: `LddEmission` / `LddSink` move to `a2kit.packages.ldd`; non-umbrella exception subclasses move to `a2kit.exceptions`. |
| **`tags={…}` decorator kwarg removed** | v0.32.0 | a2web doesn't use it (verified via grep) |
| **`surfaces=Surface.X` → `visibility="cli"\|"hidden"\|"all"`** | v0.32.0 | a2web doesn't use it (verified via grep) |
| **Typer-based CLI** | v0.32.0 — author surface unchanged | Inherit free; no work |

Free wins inherited on the bump:
- v0.27.1/2 — CLI cold-start −75% (138ms across all paths)
- v0.31.0 — WARN_ONCE on five framework-internal silent-swallow sites (better diagnostics)
- v0.32.0 — `@a2kit.list_` parameter parity (decorator kwargs match `read/write/tool`)

Two original round-3 wishes remain deferred (streaming response, `timeout=` decorator kwarg) — preserved in `docs/history/A2KIT_WISHES_DEFERRED.md`. Neither blocks anything.

## What Changes

### `pyproject.toml`

- Bump `a2kit` pin: `tag = "v0.28.0"` → `tag = "v0.32.0"`. Relax dep spec: `a2kit>=0.28,<1` → `a2kit>=0.32,<1`.
- New transitive runtime dep: `typer>=0.25,<1` (pulled by a2kit; lazy-imported, no cold-start cost).

### `src/a2web/server.py`

- Replace `@app.on_startup` / `@app.on_shutdown` with a single `@asynccontextmanager async def lifespan(app)`:
  - Pre-`yield`: `await app.warm_async_singletons()` to fail-fast on resource-open errors.
  - Post-`yield`: explicit close of each registered async-singleton (sqlite, browser_pool, llm_extractor) — wrapped in try/except so one failure doesn't strand siblings.
- Construct `App` with `lifespan=` kwarg: `app = a2kit.App("a2web", health_tool=True, lifespan=lifespan)`.
- Drop `.add_router(WebRouter())` chain from the App constructor; explicit `app.add_router(WebRouter())` after construction (composition shape unchanged in spirit, just unchained).
- Re-register the three resources via `app.singleton(T, async_factory)` (see `state.py`).
- `@app.health_check` is preserved — kept as-is, but kwarg becomes `sqlite: aiosqlite.Connection` instead of `state: AppState` once resources move out of state (see `state.py` below).

### `src/a2web/state.py`

- `AppState` shrinks to `@dataclass(slots=True) class AppState: settings: AppSettings`. The three resource fields (`sqlite`, `browser_pool`, `llm_extractor`) leave AppState entirely; they live as a2kit-managed async singletons. Phases inject the resources directly as separate kwargs alongside `state`.
- `build_state(settings)` becomes a one-liner constructor.
- Delete `SqliteResource` + `LlmExtractorResource` wrapper classes (~55 LOC).
- Per-resource async factories live in their owning packages (e.g. `open_sqlite_with_schema` in `packages/http_cache.py`, `build_browser_pool` in `packages/browser_pool.py`, `build_llm_extractor` in `llm_resource.py`).

### `src/a2web/packages/browser_pool.py`

- Add `async def build_browser_pool(settings: AppSettings) -> BrowserPool` factory that constructs and launches.
- Remove the internal `asyncio.Lock` + `_ensure()` lazy-init shim (~20 LOC). The class survives — it owns acquire / per-host caps / eviction (domain logic, not DI plumbing).

### `src/a2web/llm_resource.py`

- Replace `LlmExtractorResource` with `async def build_llm_extractor(settings, sqlite) -> Extractor | None` factory. Returns `None` on missing `[llm]` extra, missing credentials, or constructor failure.
- Open question to verify in step 0: does `app.singleton(Extractor | None, factory=...)` accept a Union as the key? If not, fall back to a tiny `LlmExtractorHandle(extractor, unavailable_reason)` dataclass and register that.

### `src/a2web/fetcher.py`

- Drop `ctx` kwarg from 9 functions: `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`, `_phase_cache_write`, `_escalate_browser`, `_dispatch_archive`, `_emit_tier_started`, `_emit_tier_ended`.
- Drop the `if ctx is None: ctx = null_context()` branch in `fetch()` (lines ~210-214). Drop the `from a2kit.testing import null_context` import.
- Replace all 16 `await a2kit.ldd.event(ctx, X)` with `await a2kit.ldd.event(X)`.
- Add resource kwargs to phases that need them (`sqlite: aiosqlite.Connection` on cache phases; `browser_pool: BrowserPool` on browser-escalate; `llm_extractor: Extractor | None` on extract-answer). `_run_pipeline` threads them down; `WebRouter.fetch` accepts them at the top.
- Drop `ctx: a2kit.ToolContext` from `FetchContext` if present.

### `src/a2web/routers.py`

- Add required ClassVars to `WebRouter`: `slug: ClassVar[str] = "web"` and `tools: ClassVar[tuple[Callable[..., Any], ...]] = (fetch,)` (placed AFTER `fetch` is defined per the v0.31 contract).
- Replace 6 `Annotated[T, a2kit.Param("…")]` → `Annotated[T, pydantic.Field(description="…")]`. Mechanical — `a2kit.Param` is gone in v0.31.
- Drop `ctx: a2kit.ToolContext` kwarg from `fetch()` signature (matches the ambient-ctx migration in fetcher.py).
- Add resource kwargs that orchestrator needs at the top: `sqlite`, `browser_pool`, `llm_extractor` injected by a2kit's container, passed into `orchestrate(...)`.

### `src/a2web/events/sinks.py`

- Update import: `from a2kit.ldd import LddEmission` → `from a2kit.packages.ldd import LddEmission` (v0.32 namespace trim).

### `src/a2web/events/__init__.py`

- Update docstring: drop `(ctx, name, **payload)` shape reference.

### `tests/`

- Replace 5 `monkeypatch.setattr(state.<resource>, ...)` sites with `async with client.override(<T>, <fake>):` blocks. Drop attendant `type: ignore[assignment]`.
- Any test that uses `ldd_state_for_call(...)` directly: add the required `ctx=` keyword (v0.29.0 breaking).
- Test client `__aenter__` enters the lifespan now — verify no test bypasses lifespan when it shouldn't.
- `tests/test_fetcher.py:283` `test_no_ctx_no_events` — delete. Behavior gone (without ctx, `a2kit.ldd.event` raises `AmbientContextMissing` per v0.29).
- **New test** `tests/test_router_schema.py` — use `TestClient.call_wire` to introspect the MCP schema and assert every user-facing kw-only param on `WebRouter.fetch` has a description ≥20 chars. Guards against contributors forgetting `pydantic.Field(description=...)` on a new param.

### `tests/test_app_state.py`

- AppState shrinks to `{settings}`. Tests that asserted resource fields exist on AppState rewrite to use `client.override(<T>, ...)` or `app.container().resolve(<T>)` instead.

### `pyproject.toml` (Ruff config)

- No pydocstyle convention pin needed (docstring pull was reverted in v0.30, so the lint guard from the old proposal is moot).

### `CLAUDE.md`

- Update the "Architecture (a2kit v0.26 mediated)" section to reference v0.32 surface: `lifespan=` kwarg, explicit Router `slug`/`tools`, `app.singleton(T, async_factory)`, ambient-ctx LDD primitives.
- Update the "Conventions" section: drop the `Annotated[T, a2kit.Param(...)]` example; replace with `Annotated[T, pydantic.Field(description="...")]`.
- No new conventions added (the docstring-pull-related guidance from the old proposal is dead).

### `docs/history/`

- Rename `docs/history/A2KIT_FEEDBACK.md` → `docs/history/A2KIT_FEEDBACK_v0.28-32.md`. Prefix with: `> Shipped in a2kit v0.28.1 + v0.29.0/.1 + v0.30.0 (docstring-pull reversion) + v0.31.0 + v0.32.0 (2026-05-12 → 2026-05-13). Migrated in change 2026-05-13-a2kit-v032-migration. Note: the docstring-pull feature shipped in v0.29.0 and reverted in v0.30.0 — our feedback round's caution about silent description drift was vindicated by upstream removal.`
- `docs/history/A2KIT_WISHES_DEFERRED.md` already in place from the previous proposal — no work needed.

## Non-goals

- **No new tools.** The MCP surface (`WebRouter.fetch`) is unchanged from a caller's POV: same args, same return type, same behavior. Only the Router class internals change (slug/tools ClassVars).
- **No fetcher logic changes.** Tier order, escalation rules, gate logic, cache semantics — all unchanged.
- **No streaming response work.** Parked.
- **No `timeout=` decorator work.** Parked.
- **No `visibility=` migration.** a2web doesn't use `surfaces=` today; verified via grep. The `fetch` tool is implicitly `"all"` (default).
- **No openspec spec-file updates** unless a spec contradicts the new shape. AppState's spec (`specs/app-state/`) likely needs a touch since AppState is shrinking; captured in `tasks.md`.

## Acceptance

1. `make check` passes (lint + ty + 374-test suite, ≥85% coverage gate holds).
2. `a2web serve` starts cleanly against `a2kit v0.32.0` — no FastMCP `NotImplementedError`, no `TypeError` from missing Router `slug`/`tools` or wrong lifespan signature.
3. `a2web serve` registers as a global Claude Code MCP server; `mcp__a2web__fetch` shows up in the agent's tool list. (Original blocker.)
4. CLI smoke (`a2web web fetch --url=<known-hard-URL>`) returns a populated `FetchResponse` with diagnostics.
5. `tests/test_router_schema.py` (new) passes — every user-facing `fetch` param has a substantive description in the MCP schema.

## Risks

- **Lifespan rewrite touches the most load-bearing file.** `server.py` is the App composition root; getting `lifespan=` shape wrong means startup fails entirely. Mitigation: write the lifespan block to mirror the v0.32 README's canonical example exactly; verify with a fresh `python -c "from a2web.server import app"` before running tests.
- **Resource cleanup ordering matters.** With `@on_shutdown` gone, the `finally` block in lifespan must close resources in the reverse-of-open order (sqlite last — others may depend on it for cache reads at shutdown). Wrap each close in try/except so one failure doesn't strand siblings.
- **Ambient ctx migration is many-site mechanical.** 16 `a2kit.ldd.event` call sites. v0.29's now-loud `AmbientContextMissing` will surface any missed site at runtime — fail-loud is the safety net.
- **Docstring pull removed mid-flight.** If you started writing `Args:` blocks for tool params anywhere, those won't populate. Verified via grep: a2web hasn't done this. Safe.
- **Two breaking releases on the same day.** v0.30, v0.31, v0.32 all shipped 2026-05-12 → 2026-05-13. Risk of a v0.33 dropping again before this lands. Mitigation: don't rebase mid-execution unless it fixes a blocker; finish the migration on v0.32.0, file feedback after, plan next round if needed.
- **`Union` as singleton key (`Extractor | None`).** Unverified. If unsupported, falls back to `LlmExtractorHandle` dataclass; either path works, just affects shape. Verify in task 0a before step 2.

## Out-of-scope items captured elsewhere

- Streaming response API (round-3 wish 2) → `docs/history/A2KIT_WISHES_DEFERRED.md`
- `timeout=` decorator kwarg (round-3 wish 1) → same file
- a2kit-internal openspec follow-ups worth watching → same file (`align-context-method-signatures`, `rebuild-test-client-on-real-context`)
