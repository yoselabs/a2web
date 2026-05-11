## 1. Phase A — a2kit v0.23 → v0.26 migration

### 1.1 Pin upgrade and import audit
- [ ] 1.1.1 Bump `a2kit>=0.23,<1` → `a2kit>=0.26,<1` in `pyproject.toml`; update `[tool.uv.sources]` tag to `v0.26.0` (or move to PyPI if published).
- [ ] 1.1.2 Run `uv sync --all-extras`; verify no resolver errors.
- [ ] 1.1.3 `grep -rn "import a2kit\|from a2kit" src/ tests/` — audit every touch point against v0.26 surface; flag any usage of removed/renamed APIs (`ctx.event`, `register_state`, `app.container().resolve(...connection=None)`, `_ProgressCtx` Protocol).
- [ ] 1.1.4 Skim `OPERATIONAL_CONTRACTS.md` for Q1/Q2/Q3/Q5/Q6 — confirm we understand cancellation, timeout, multi-App, error envelope, streaming contracts before changing code.

### 1.2 state.py rewrite
- [ ] 1.2.1 Replace `register_state` with `build_state(settings: AppSettings | None = None) -> AppState` factory function.
- [ ] 1.2.2 Make `AppState.sqlite` and `AppState.proxy_pool` non-Optional; drop `sqlite_lock`, `browser_lock`, `proxy_lock`, `extras` fields.
- [ ] 1.2.3 Delete `ensure_sqlite`, `ensure_proxy_pool`, `ensure_browser_pool`, `_atexit_close`, `bootstrap_state_for_test`, `teardown_state_for_test`.
- [ ] 1.2.4 Keep lazy-open inside `BrowserTier.fetch` for `browser_pool` (Camoufox is optional dep, must not crash startup if missing).
- [ ] 1.2.5 Verify `state.py` is under ~80 LOC after the rewrite (down from 152).

### 1.3 server.py imperative composition
- [ ] 1.3.1 Compose `app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())` then imperative `app.singleton(AppState, factory=build_state)`.
- [ ] 1.3.2 Add `@app.on_startup` opening sqlite via `open_sqlite_with_schema(state.settings)`.
- [ ] 1.3.3 Add `@app.on_shutdown` closing sqlite + browser_pool (if non-None).
- [ ] 1.3.4 Add `@app.health_check` for sqlite open state.
- [ ] 1.3.5 Add `app.ldd.add_sink(otel_sink)` registration (otel_sink defined in step 1.5).
- [ ] 1.3.6 Confirm no fluent chain spans more than 2 lines in `server.py`.

### 1.4 routers.py tool decorator + docstring
- [ ] 1.4.1 Add `@a2kit.read(Surface.ALL, idempotent=True, open_world=True, title="Fetch Web Page")` to `WebRouter.fetch`.
- [ ] 1.4.2 Add `Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")]` to `url` kwarg.
- [ ] 1.4.3 Rewrite `fetch` docstring per the documented contract: short first-line summary + multi-paragraph body describing the cascade, escalation behavior, return shape, verdict meanings.
- [ ] 1.4.4 Delete `EventBus`, `mcp_recv`, `otel_recv`, the `anyio.create_task_group()` wrapping in the tool body. Tool body becomes a 1-line delegate: `return await orchestrate(url, state=state, ctx=ctx)`.

### 1.5 events/ collapse
- [ ] 1.5.1 Delete `events/bus.py` entirely.
- [ ] 1.5.2 Delete `mcp_progress_sink` and `_ProgressCtx` Protocol in `events/sinks.py`; file shrinks to `otel_sink` (~15 LOC) + helper formatters as needed.
- [ ] 1.5.3 Keep `events/types.py` for `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, add new `TierHeartbeat`.
- [ ] 1.5.4 Register all five event types on `app.ldd.events` in `server.py` (or a `_register_events` helper called from there).
- [ ] 1.5.5 Verify `otel_sink` matches a2kit's `Sink` protocol: async callable receiving `LddEmission`.

### 1.6 fetcher.py emission migration
- [ ] 1.6.1 Drop the `bus: EventBus | None` parameter from `fetcher.fetch(...)` and `_run_pipeline(...)`. Signature becomes `fetch(url, *, state, ctx)`.
- [ ] 1.6.2 Replace every `await bus.publish(...)` with `await a2kit.ldd.event(ctx, ...)` (or typed-emit via `app.ldd.events.emit_typed`).
- [ ] 1.6.3 Delete the `_publish(bus, event)` shim.
- [ ] 1.6.4 Run the existing test suite with mock ctx; iterate until emissions reach the expected sinks.

### 1.7 TierHeartbeat in slow tiers
- [ ] 1.7.1 In `tiers/browser.py`, add a background task that emits `TierHeartbeat(step="browser", elapsed_in_tier_ms=..., detail={"target_url": url})` every 2s during page-load wait.
- [ ] 1.7.2 Cancel the heartbeat task in the tier's `finally` block (cleanup-on-timeout per Q1 contract).
- [ ] 1.7.3 In `tiers/archive.py`, emit one `TierHeartbeat` per hedged-request boundary (after Wayback responds and after archive.ph responds).
- [ ] 1.7.4 Add test `test_tier_heartbeat.py` asserting heartbeats fire during simulated slow tier; stop on completion; reach the test client's `events` list.

### 1.8 Tests migration to a2kit.testing.client
- [ ] 1.8.1 Migrate `test_fetcher.py` (the most representative integration test) from `fetcher.fetch(...)` to `async with client(app) as c: result = await c.invoke("web.fetch", url=...)`.
- [ ] 1.8.2 Migrate `test_archive_escalation.py`, `test_browser_escalation.py`, `test_after_tier_execution.py` to client invocation.
- [ ] 1.8.3 Migrate `test_app_composition.py`, `test_app_state.py` to use `Container.resolve_sync` / `a2kit.testing.peek` for state inspection; drop the async-resolve contortions.
- [ ] 1.8.4 Rewrite `tests/conftest.py` — drop `REGISTRY` monkey-patching of archive/browser; provide fake tiers via `app.provide(...)` overrides in the test app.
- [ ] 1.8.5 Add new tests: `test_router_dispatch.py` (router-layer invocations via client), `test_health.py` (health check exits 0 when sqlite open, non-zero otherwise), `test_lifecycle.py` (startup opens sqlite; shutdown closes it; multi-App canary).
- [ ] 1.8.6 Maintain ≥85% coverage gate.

### 1.9 Phase A green-bar
- [ ] 1.9.1 `make lint` clean.
- [ ] 1.9.2 `make ty` clean (zero `# ty: ignore`).
- [ ] 1.9.3 `make test` green; coverage ≥85%.
- [ ] 1.9.4 `make dev` boots cleanly; `a2web health` exits 0; `a2web web fetch --url=https://example.com` returns a response.
- [ ] 1.9.5 Update `CHANGELOG.md` with the BREAKING note (a2kit migration); update `BACKLOG.md` (no items shipped or deferred yet — Phase B handles that).
- [ ] 1.9.6 Tag and merge Phase A as one PR before starting Phase B.

## 2. Phase B — OSS adoption

### 2.1 B-spike: hishel curl_cffi shim
- [ ] 2.1.1 Add `hishel` to `pyproject.toml` (lockfile only, no usage yet).
- [ ] 2.1.2 In a small `src/a2web/cache/_shim.py`, prototype `curl_response_to_httpcore(resp) -> httpcore.Response` and `to_curl_request(req) -> httpcore.Request`.
- [ ] 2.1.3 Write a smoke test that calls `hishel.Controller(...).handle_response(...)` on a synthetic curl response; assert no exceptions, cache entry written.
- [ ] 2.1.4 Measure shim LOC. **Decision gate:** if ≤ 80 LOC and smoke passes, proceed to 2.2; if > 80 LOC or unsolved edge cases, abort hishel adoption — defer to v0.2, skip section 2.2 entirely, document the abort in BACKLOG.

### 2.2 hishel cache replacement
- [ ] 2.2.1 Delete `src/a2web/cache/sqlite_cache.py` — schema, `compute_profile_hash`, `cache_get`, `cache_put`, `is_live_only`, `_ttl_for`, `CacheRow`.
- [ ] 2.2.2 In `src/a2web/cache/__init__.py`, build the hishel `Controller` + `SQLiteStorage` (storage path: `~/.a2web/hishel.sqlite` or honor `A2WEB_CACHE_DIR`).
- [ ] 2.2.3 Expose adapter functions: `try_from_cache(url, request) -> CachedResponse | None`, `store_response(url, request, response) -> None`.
- [ ] 2.2.4 Honor `state.settings.live_only_hosts` — bypass the controller entirely for matching hosts.
- [ ] 2.2.5 Rewire `_phase_cache_check` and `_phase_cache_write` in the orchestrator to use hishel adapter calls.
- [ ] 2.2.6 Delete `tests/test_cache.py`; rewrite as `test_cache_shim.py` against the hishel-backed adapter.
- [ ] 2.2.7 Audit for `aiosqlite` imports; if zero remain, remove from `pyproject.toml`.

### 2.3 stdlib RotatingFileHandler for NDJSON log
- [ ] 2.3.1 Delete `src/a2web/log/writer.py`'s hand-rolled async writer, rotation, gzip logic.
- [ ] 2.3.2 Add `build_log_handler(settings: AppSettings) -> logging.Handler` returning a configured `RotatingFileHandler(filename=log_path(), maxBytes=16*1024*1024, backupCount=20, rotator=_gzip_rotator)`.
- [ ] 2.3.3 Define `_gzip_rotator(source, dest)` callback (~5 LOC): `gzip.open(dest+'.gz', 'wb')` + `shutil.copyfileobj`.
- [ ] 2.3.4 `LogWriter` becomes a thin wrapper that formats `LogRecord` to JSON via structlog's `JSONRenderer` (or a `record_to_json` helper) and emits through the handler.
- [ ] 2.3.5 Preserve `state.log_writer.write_record(record)` interface so the orchestrator's call site doesn't change.
- [ ] 2.3.6 Rewrite `tests/test_log_writer.py`, `tests/test_log_rotation.py` against the new implementation.

### 2.4 trafilatura metadata consolidation
- [ ] 2.4.1 Delete `src/a2web/extract/htmldate_ext.py`.
- [ ] 2.4.2 Delete `src/a2web/extract/metadata.py`.
- [ ] 2.4.3 Rewrite `src/a2web/extract/trafilatura_ext.py`:
  - Replace the current `extract` call with `bare_extraction(html, url=url, with_metadata=True, output_format="markdown", include_comments=False, include_tables=False)`.
  - `ExtractResult` gains `published: date | None` (from trafilatura metadata), `meta: dict[str, str]` (flattened OG/Twitter/JSON-LD).
  - Map trafilatura's metadata field names to the v0.1.0 key set (`og.type`, `og.image`, etc.).
- [ ] 2.4.4 Update orchestrator: drop separate `find_published(...)` and `parse_metadata(...)` calls — single `extract_markdown(...)` returns everything.
- [ ] 2.4.5 Remove `htmldate` from `pyproject.toml`.
- [ ] 2.4.6 Rewrite `tests/test_extract.py`, `tests/test_metadata.py` against the consolidated path; delete htmldate-specific tests.

### 2.5 fit-md validation gate then deletion
- [ ] 2.5.1 Write `tests/test_fit_md_regression.py`: load every existing fit-md fixture, run trafilatura with `prune_xpath` + `include_comments=False`, compare token counts to v0.1.0 fit-md output.
- [ ] 2.5.2 **Decision gate:** if ≤ 5% of fixtures regress by > 20%, proceed to 2.5.3 (full delete). Otherwise demote to 2.5.4 (partial-drop).
- [ ] 2.5.3 (Full delete path) Delete `src/a2web/extract/pruning_filter.py`. Delete `_phase_fit` from the orchestrator. `FetchResponse.fit_md` is set equal to `content_md` post-extraction. Update tests.
- [ ] 2.5.4 (Partial-drop path, only if 2.5.2 fails) Shrink `pruning_filter.py` to ≤ 40 LOC implementing a minimal post-filter. Keep `_phase_fit`. Add a backlog item to revisit.

### 2.6 purgatory for proxy quarantine
- [ ] 2.6.1 In `src/a2web/proxy/pool.py` (or wherever ProxyPool lives pre-packaging), replace the in-memory health state machine with a `purgatory.AsyncCircuitBreakerFactory` keyed by proxy URL.
- [ ] 2.6.2 Configure breakers with `default_threshold=3, default_ttl=600.0` to match the v0.1.0 contract.
- [ ] 2.6.3 Map breaker states to `HealthState`: CLOSED → alive, OPEN → quarantined, HALF_OPEN → alive (post-timeout probe).
- [ ] 2.6.4 Update `ProxyPool.acquire` and `ProxyPool.report` to consult/update the breaker, not the hand-rolled state.
- [ ] 2.6.5 Update tests; verify the v0.1.0 scenarios still pass.

### 2.7 aiometer for hedged archive requests
- [ ] 2.7.1 Add `aiometer>=0.6,<1` to `pyproject.toml`.
- [ ] 2.7.2 In `tiers/archive.py`, replace the hand-rolled `anyio.create_task_group` race with `aiometer.run_any([_fetch_wayback, _fetch_archiveph])`.
- [ ] 2.7.3 Confirm cancellation semantics: when one upstream returns OK, the other is cancelled per `aiometer` docs.
- [ ] 2.7.4 Update tests to assert race behavior still holds; integrate with TierHeartbeat (one heartbeat per upstream completion).

### 2.8 Phase B green-bar
- [ ] 2.8.1 `make check` clean (lint + ty + test, coverage ≥85%).
- [ ] 2.8.2 `make dev` smoke test: `a2web web fetch --url=https://example.com`, `... --url=https://www.reddit.com/r/...`, `... --url=<arxiv abs page>`, `... --url=<a known-paywall fixture>` (verify archive escalation), `... --url=<a known-block fixture>` (verify gate behavior).
- [ ] 2.8.3 Update `CHANGELOG.md` with BREAKING note: cache file format changes; users get a fresh cache on first run. Mention `htmldate` removed, `aiosqlite` removed (if applicable), `hishel` added, `aiometer` added.
- [ ] 2.8.4 Update `BACKLOG.md`: any deferred items (e.g., partial-drop fit-md if 2.5.4 fired) added.
- [ ] 2.8.5 Merge Phase B as one PR.

## 3. Phase C — internal magic removal

### 3.1 Typed TierResult extras
- [ ] 3.1.1 In `src/a2web/tiers/__init__.py`, expand `TierResult` with typed fields per spec D6:
  - `pre_rendered: Rendered | None`, `from_archive: bool`, `snapshot_age_days: int | None`, `from_browser: bool`, `js_executed: bool`, `browser_wall_ms: int | None`, `browser_bytes: int | None`, `operator_hint: OperatorHint | None`, `no_match: bool`, `skipped: bool`, `handler_name: str | None`, `conditional_hit: bool`.
- [ ] 3.1.2 Define `Rendered` dataclass at module scope: `content_md: str`, `title: str | None`, `byline: str | None`, `headings: list[Heading]`.
- [ ] 3.1.3 Delete `tier_extras: dict[str, Any]` field.
- [ ] 3.1.4 Update every tier (`raw.py`, `jina.py`, `archive.py`, `browser.py`, `site_handler.py`, all handlers) to populate typed fields instead of dict.
- [ ] 3.1.5 Update orchestrator: every `tier_result.tier_extras.get("X")` becomes a typed-field read.
- [ ] 3.1.6 Update tests that asserted against `tier_extras["..."]`.

### 3.2 Single `_dispatch_archive` helper
- [ ] 3.2.1 Define `_dispatch_archive(url, *, state, ctx, fc: FetchContext) -> ArchiveOutcome` in `fetcher.py`. `ArchiveOutcome` carries `installed: bool`, `body`, `content_type`, `final_url`, `pre_rendered`, `status_code`, `diagnostic_row` (or `None` when archive failed).
- [ ] 3.2.2 Lift both archive-dispatch blocks (after-tier ~lines 276–315; after-gate ~lines 502–558) into calls to the helper.
- [ ] 3.2.3 Move the per-fetch `archive_dispatches` cap counter into `FetchContext` (see 3.4) and consult/increment inside the helper.
- [ ] 3.2.4 Verify orchestrator drops ~80 LOC; helper adds ~50 LOC; net negative.

### 3.3 Named phase functions
- [ ] 3.3.1 Define `FetchContext` dataclass at module scope (see 3.4 below).
- [ ] 3.3.2 Define `_phase_cache_check(state, fc) -> None`, `_phase_tier_loop(state, ctx, fc) -> None`, `_phase_extract(fc) -> None`, `_phase_gate(fc) -> None`, `_phase_escalate_browser(state, ctx, fc) -> None`, `_phase_escalate_archive(state, ctx, fc) -> None`, `_phase_fit(fc) -> None` (or stub if 2.5.3 deletes it), `_phase_cache_write(state, fc) -> None`.
- [ ] 3.3.3 Reorganize `_run_pipeline(...)` to call the phase functions in sequence with early-exit on cache hit.
- [ ] 3.3.4 Delete every `# Phase 4.<digit>` comment.
- [ ] 3.3.5 Verify `_run_pipeline` body ≤ 120 lines (down from ~500).

### 3.4 FetchContext encapsulation
- [ ] 3.4.1 `FetchContext` carries: `url: str`, `body: bytes`, `final_url: str`, `content_type: str`, `status_code: int`, `tier_used: str | None`, `final_verdict: Verdict`, `etag: str | None`, `last_modified: str | None`, `pre_rendered_payload: Rendered | None`, `diagnostics: list[Diagnostic]`, `url_rewrites: int`, `archive_dispatches: int`, `browser_dispatches: int`, `cache_state: CacheState`, `cached_row: CachedResponse | None`, `started_at: datetime`, `start_perf: float`, plus extraction outputs (`content_md`, `title`, `byline`, `headings`, `links`, `meta_dict`, `published`, `fit_md`).
- [ ] 3.4.2 Each phase function takes `fc: FetchContext` and mutates fields rather than 8+ parameters.
- [ ] 3.4.3 Tests verifying phase-level behavior (`test_fetcher_phases.py`) can construct a `FetchContext` directly and invoke one phase in isolation.

### 3.5 Unified `tier_used` identity
- [ ] 3.5.1 Define `_resolve_tier_used(fc: FetchContext) -> str` with the rule from spec D9.
- [ ] 3.5.2 Delete every other site that writes `FetchResponse.tier`; this resolver is the only writer at response-build time.
- [ ] 3.5.3 Add regression test `test_tier_identity.py` asserting all six rule cases produce the right string.

### 3.6 Escalation-dispatch documentation
- [ ] 3.6.1 Remove the "registered but not in TIER_ORDER" footnote comments from `tiers/__init__.py`, `tiers/archive.py`, `tiers/browser.py`.
- [ ] 3.6.2 Replace with a single docstring on `tiers/__init__.py` that explicitly names the escalation-dispatch contract.

### 3.7 Phase C green-bar
- [ ] 3.7.1 `make check` clean.
- [ ] 3.7.2 Visual review: open `fetcher.py`; confirm it reads top-down as a sequence of named phases rather than one monolithic loop.
- [ ] 3.7.3 Merge Phase C as one PR.

## 4. Phase D — workspace packaging

### 4.1 Workspace skeleton
- [ ] 4.1.1 Add `[tool.uv.workspace]` table to root `pyproject.toml` with `members = ["packages/*"]`.
- [ ] 4.1.2 Create `packages/proxy-pool/`, `packages/browser-pool/`, `packages/block-detector/` with `pyproject.toml` + `src/<name>/__init__.py` + `tests/`.
- [ ] 4.1.3 Each `pyproject.toml`: own name, version, description, runtime deps (proxy-pool: purgatory; browser-pool: playwright + camoufox optional extras; block-detector: none), `[build-system]` with hatchling.
- [ ] 4.1.4 Root `pyproject.toml` declares each as workspace dep: `proxy-pool = { workspace = true }`, etc. Add `[tool.uv.sources]` entries.
- [ ] 4.1.5 `uv sync --all-extras` from root — verify all three resolve to workspace paths, lockfile records `source = "workspace"`.

### 4.2 Extract block-detector (smallest, no deps)
- [ ] 4.2.1 Move `src/a2web/gate/block_detector.py` → `packages/block-detector/src/block_detector/detector.py`.
- [ ] 4.2.2 Define package-native types in `packages/block-detector/src/block_detector/types.py`: `BlockVerdict`, `GateResult`, `SuggestedTier`.
- [ ] 4.2.3 Expose public API via `packages/block-detector/src/block_detector/__init__.py`.
- [ ] 4.2.4 Build adapter at `src/a2web/gate/__init__.py`: import `block_detector`, translate `block_detector.GateResult` to a2web's existing GateResult format (or update orchestrator to consume package types directly if cleaner).
- [ ] 4.2.5 Move `tests/test_gate.py` to `packages/block-detector/tests/`.
- [ ] 4.2.6 Lint check: `grep -r "from a2web\|import a2web" packages/block-detector/src/` produces zero matches.
- [ ] 4.2.7 `cd packages/block-detector && uv run pytest` passes independently.

### 4.3 Extract proxy-pool
- [ ] 4.3.1 Move `src/a2web/proxy/policy.py`, `src/a2web/proxy/pool.py` → `packages/proxy-pool/src/proxy_pool/`.
- [ ] 4.3.2 Define package-native types in `packages/proxy-pool/src/proxy_pool/types.py`: `HealthState`, `ResolvedRoute`, `ProxyHandle`.
- [ ] 4.3.3 Expose public API via `packages/proxy-pool/src/proxy_pool/__init__.py`.
- [ ] 4.3.4 Adapter at `src/a2web/proxy/__init__.py`: import `proxy_pool`, translate where needed for orchestrator's diagnostic-row consumption.
- [ ] 4.3.5 Move `tests/test_proxy_policy.py`, `tests/test_proxy_pool.py` → `packages/proxy-pool/tests/`.
- [ ] 4.3.6 Lint + isolation tests pass.

### 4.4 Extract browser-pool
- [ ] 4.4.1 Move `src/a2web/browser/pool.py` → `packages/browser-pool/src/browser_pool/pool.py`.
- [ ] 4.4.2 Define package-native types in `packages/browser-pool/src/browser_pool/types.py`: `PageResult`, `PoolStats` if helpful.
- [ ] 4.4.3 Expose public API; declare `playwright` as required dep, `camoufox` as `[camoufox]` optional extra.
- [ ] 4.4.4 Adapter at `src/a2web/browser/__init__.py`: lazy-open pool (Camoufox is optional), translate package result types.
- [ ] 4.4.5 `BrowserTier` stays in a2web's tier tree (it's domain logic); pool is package-owned.
- [ ] 4.4.6 Move `tests/test_browser_pool.py` → `packages/browser-pool/tests/`. `tests/test_browser_tier.py` stays in a2web.
- [ ] 4.4.7 Lint + isolation tests pass.

### 4.5 Makefile + CI rewiring
- [ ] 4.5.1 Update `Makefile`: `make lint`, `make ty`, `make test`, `make check` aggregate across a2web + every workspace package. Failure in any subdir fails the aggregate.
- [ ] 4.5.2 Update `.github/workflows/*` (or whatever CI lives) to run the workspace-aware target.
- [ ] 4.5.3 Add a custom lint check (or use `flake8-tidy-imports` banlist) that fails if any `packages/*/src/` file imports anything from `a2web`. This enforces the boundary.

### 4.6 Phase D green-bar
- [ ] 4.6.1 `make check` from root: clean. Coverage gate maintained.
- [ ] 4.6.2 `cd packages/<each> && uv run pytest`: each passes independently.
- [ ] 4.6.3 `make dev` smoke test: `a2web web fetch --url=...` works end-to-end with packages providing the implementations.
- [ ] 4.6.4 Update `CHANGELOG.md`: workspace layout note; non-breaking for external consumers.
- [ ] 4.6.5 Merge Phase D as one PR.

## 5. Post-migration housekeeping

- [ ] 5.1 Delete `A2KIT_FEEDBACK.md` (or move to `docs/history/`) — every ask is closed; file is now historical.
- [ ] 5.2 Update `CLAUDE.md` to reflect the new architecture: imperative composition, ldd sinks, hishel cache, three workspace packages, etc.
- [ ] 5.3 Update `README.md` if it has architectural diagrams.
- [ ] 5.4 Send a "post-migration debrief" to a2kit dev if anything turned up that isn't covered by `OPERATIONAL_CONTRACTS.md`.
- [ ] 5.5 Tag a release (`v0.2.0` given the cache-format break + LOC reduction + workspace layout).
- [ ] 5.6 Update `BACKLOG.md`: remove any items this change shipped; add any items deferred (chunked content_md streaming, partial-drop fit-md if applicable, etc.).
