# Tasks — a2kit v0.29 migration

Step ordering is load-bearing — see `design.md` "Migration order recap". Don't reorder steps 0 → 5 without thinking about why.

---

## Step 0 — Pin bump

- [ ] 0a. Read v0.29.x README "Resource pattern" + testing sections; verify async-singleton API exactly matches the design.md sketches. Note any surface delta (especially: does `app.singleton(Union[T, None], factory)` work, or do we need a handle dataclass for `Extractor | None`?).
- [ ] 0b. In `pyproject.toml`: bump `[tool.uv.sources] a2kit.tag` from `v0.28.0` to `v0.29.1`. Keep version spec `a2kit>=0.28,<1` (or relax to `>=0.29,<1`).
- [ ] 0c. `uv sync --all-extras`. Confirm install clean.
- [ ] 0d. Run `make check`. Capture the failure surface (expected: many `AmbientContextMissing` raises in fetcher tests, possibly `null_context` import errors). This is the migration's red baseline.

## Step 1 — Ambient `ctx` migration

- [ ] 1a. Strip `ctx` kwarg from `fetch()` entrypoint signature in `fetcher.py`. Remove the `if ctx is None: from a2kit.testing import null_context; ctx = null_context()` branch (lines ~210-214).
- [ ] 1b. Strip `ctx` kwarg from all 9 phase / helper signatures in `fetcher.py`:
  - `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`, `_phase_cache_write`
  - `_escalate_browser`, `_dispatch_archive`
  - `_emit_tier_started`, `_emit_tier_ended`
- [ ] 1c. Replace all `await a2kit.ldd.event(ctx, X)` with `await a2kit.ldd.event(X)` (16 sites per grep). One sed pass + verify by grep.
- [ ] 1d. Drop `from a2kit.testing import null_context` if still imported anywhere.
- [ ] 1e. Drop `ctx` from `FetchContext` dataclass if present (check `fetcher.py` for the FetchContext definition).
- [ ] 1f. Update `events/__init__.py` docstring — drop `(ctx, name, **payload)` shape reference.
- [ ] 1g. Update `fetcher.py` line 194 + 259 docstring comments referencing `a2kit.ldd.event(ctx, ...)`.
- [ ] 1h. Update `routers.py` — drop `ctx: a2kit.ToolContext` kwarg from `WebRouter.fetch`. Drop the now-unused `import a2kit` line if no other a2kit reference remains (it does — `@a2kit.read`, `a2kit.Router`).
- [ ] 1i. `tests/test_fetcher.py:283` — delete the `test_no_ctx_no_events` test (semantics gone, see design.md decision 2).
- [ ] 1j. `make check`. Should be green on fetcher tests; resource tests will still fail next step.

## Step 2 — Resource collapse to async singletons (Path B from design.md)

- [ ] 2a. `state.py`: shrink `AppState` to `@dataclass(slots=True) class AppState: settings: AppSettings`. Delete the three resource fields. Simplify `build_state(settings)` to one-liner.
- [ ] 2b. `packages/http_cache.py`: keep `open_sqlite_with_schema(settings)` as the async factory. Delete `SqliteResource` class (~25 LOC). Adjust any module-level exports.
- [ ] 2c. `packages/browser_pool.py`: add `build_browser_pool(settings)` async factory that does the launch. Remove the internal `asyncio.Lock` + `_ensure()` from `BrowserPool` (~20 LOC). `BrowserPool` class survives with domain methods (`acquire`, etc.).
- [ ] 2d. `llm_resource.py`: replace `LlmExtractorResource` with `build_llm_extractor(settings, sqlite)` async factory returning `Extractor | None`. Delete the class. If `app.singleton(Extractor | None, ...)` doesn't accept Union keys (per task 0a verification), introduce a tiny `LlmExtractorHandle(extractor, unavailable_reason)` dataclass instead.
- [ ] 2e. `server.py`: register all three with the new async-singleton API:
  - `app.singleton(aiosqlite.Connection, factory=open_sqlite_with_schema)`
  - `app.singleton(BrowserPool, factory=build_browser_pool)`
  - `app.singleton(Extractor | None, factory=build_llm_extractor)` (or `LlmExtractorHandle` per 2d)
- [ ] 2f. Update `@app.on_startup` hooks if any pre-warm resources via `_ensure()` — async singletons resolve on first inject, no explicit warm needed. If you want fail-fast on startup, await each singleton via container resolve inside the hook.
- [ ] 2g. Update `@app.health_check` for sqlite — adjust kwargs from `state: AppState` to `sqlite: aiosqlite.Connection` (or keep state and add sqlite as a sibling kwarg).
- [ ] 2h. `fetcher.py` phase signatures: add resource kwargs to phases that need them. E.g.:
  - `_phase_cache_check(fc, *, sqlite: aiosqlite.Connection)`
  - `_phase_cache_write(fc, *, sqlite: aiosqlite.Connection)`
  - browser-escalate path takes `browser_pool: BrowserPool`
  - extract-answer path takes `llm_extractor: Extractor | None`
- [ ] 2i. Update `_run_pipeline` (the 12-line coordinator) to thread the right kwargs into each phase. a2kit dispatches `state` + resources separately on the tool entry; we propagate them into phases.
- [ ] 2j. `routers.py::WebRouter.fetch` signature: keep `state: AppState`, add resource kwargs needed by the orchestrator's top-level. Pass them down into `orchestrate(...)`.
- [ ] 2k. Grep for `state.sqlite`, `state.browser_pool`, `state.llm_extractor` — should be zero hits after this step.
- [ ] 2l. Grep for `._ensure()` — should be zero hits.
- [ ] 2m. `make check`. Tests with `monkeypatch.setattr(state.<resource>, ...)` will fail; that's step 3.

## Step 3 — Test override sweep

- [ ] 3a. Inventory the 5 `monkeypatch.setattr(state.<resource>, ...)` sites:
  ```
  grep -rn "monkeypatch.setattr(state\." tests/
  ```
- [ ] 3b. For each: replace with `async with client.override(<T>, <fake>):` context. Drop the attendant `type: ignore[assignment]`.
- [ ] 3c. Search for any other `setattr(state, "<resource>", ...)` / `state.<resource> = ...` test patterns and migrate.
- [ ] 3d. Any tests that use `ldd_state_for_call(...)` directly: add the required `ctx=` keyword per v0.29.0 changelog.
- [ ] 3e. `make check`. Should be fully green for the migration so far.

## Step 4 — Docstring pull + 3 guards (do all four sub-steps or none)

- [ ] 4a. `routers.py::WebRouter.fetch` — strip `Annotated[T, a2kit.Param(...)]` from all 6 user-facing params. Move each description verbatim into the docstring's `Args:` section. Preserve top-level prose ("Fetch web content via an adaptive cascade…") unchanged. Reference `docs/history/A2KIT_FEEDBACK_v0.27.md` § "Gap 4 — Param verbosity" Option A example for the target shape.
- [ ] 4b. **Guard 1.** `pyproject.toml`: add
  ```toml
  [tool.ruff.lint.pydocstyle]
  convention = "google"
  ```
  Run `make lint` — expect zero new violations; existing docstrings are already Google-compatible.
- [ ] 4c. **Guard 2.** Add `tests/test_router_schema.py` with the param-description completeness test (design.md decision 3 — verify the exact `_meta` introspection call against v0.29.1 docs first). Assert every user-facing kw-only param description ≥20 chars.
- [ ] 4d. **Guard 3.** `CLAUDE.md`: add one line under "Conventions" — `Args:` prose in `@a2kit.read/list_/write`-decorated tools is **agent-facing tool guidance**. Include heuristics (when to pass, when not, payload cost, default rationale), not just type restatement.
- [ ] 4e. `make check`. Verify the new test passes and Ruff is clean.

## Step 5 — Validation

- [ ] 5a. `make check` — final green run. Confirm coverage ≥85%.
- [ ] 5b. `make dev` (or `uv run a2web serve`) — start MCP server. Confirm no `NotImplementedError` from FastMCP, server stays up.
- [ ] 5c. CLI smoke — pick 3 URLs that exercise different tiers, e.g.:
  ```
  uv run a2web web fetch --url=https://news.ycombinator.com   # handler tier
  uv run a2web web fetch --url=https://arxiv.org/abs/2310.06825 # handler tier
  uv run a2web web fetch --url=https://www.example.com         # raw tier
  ```
  Confirm each returns populated `FetchResponse` with diagnostics.
- [ ] 5d. **The acceptance test.** Register `a2web serve` as a global Claude Code MCP server (the original blocker):
  ```
  claude mcp remove a2web -s user 2>/dev/null
  claude mcp add a2web -s user -- uv --directory /Users/iorlas/Workspaces/a2web run a2web serve
  claude mcp list
  ```
  Confirm `a2web: ... ✓ Connected`.
- [ ] 5e. From a fresh Claude Code session, confirm `mcp__a2web__fetch` appears in the tool list and successfully returns content for a test URL.

## Step 6 — Documentation + closeout

- [ ] 6a. Rename `docs/history/A2KIT_FEEDBACK.md` → `docs/history/A2KIT_FEEDBACK_v0.28.md`. Prefix with a single line: `> Shipped in a2kit v0.28.1 (FastMCP fix, _meta docs) + v0.29.0 (everything else) + v0.29.1 (cleanup bundle). a2web migrated in change 2026-05-13-a2kit-v029-migration.`
- [ ] 6b. `docs/history/A2KIT_WISHES_DEFERRED.md` is already in place; no work needed.
- [ ] 6c. Update `CHANGELOG.md` — new `[Unreleased]` (or `v0.7.0`) entry summarizing: a2kit pin v0.28.0 → v0.29.1, ~175 LOC adapter shim deleted, ambient-ctx migration, async-singleton resource collapse, MCP server now works as global Claude Code MCP server.
- [ ] 6d. Update `BACKLOG.md` if any item there is closed by this migration. (Check for items mentioning ctx threading, Resource boilerplate, monkeypatch test seams.)
- [ ] 6e. Commit at the end of each step (steps 1, 2, 3, 4 are natural commit boundaries; step 5 is verification with no diff; step 6 is one doc commit).

---

## Definition of done

- [ ] All checkboxes above marked done.
- [ ] `make check` green, coverage ≥85%.
- [ ] `claude mcp list` shows `a2web: ... ✓ Connected`.
- [ ] `mcp__a2web__fetch` reachable from a fresh Claude Code session.
- [ ] `docs/history/A2KIT_FEEDBACK.md` renamed; `A2KIT_WISHES_DEFERRED.md` preserves the two remaining round-3 wishes.
- [ ] No `state.sqlite` / `state.browser_pool` / `state.llm_extractor` references anywhere.
- [ ] No `._ensure()` calls anywhere.
- [ ] No `Annotated[..., a2kit.Param(...)]` in `routers.py`.
- [ ] No `monkeypatch.setattr(state.<resource>, ...)` in tests.
- [ ] No `null_context()` import in `fetcher.py`.
- [ ] Ruff `pydocstyle.convention = "google"` enforced.
- [ ] The new `tests/test_router_schema.py` exists and passes.
