## Why

a2kit v0.24–v0.26 shipped lifecycle hooks, singleton DI, ldd subscription sinks, in-process test client, tool annotations, health probe, and OPERATIONAL_CONTRACTS — every blocking ask from rounds 1–3 of our feedback. With that delivered, ~190 LOC of workaround scaffolding in a2web becomes dead weight (atexit + fresh-event-loop, three `ensure_X` lazy-lock patterns, `register_state` closure, `EventBus` + two sinks, `bootstrap_state_for_test`, the `_ProgressCtx` Protocol, model-scope antipattern comments).

Parallel to that, a research pass over hand-rolled subsystems identified four OSS libraries that replace ~510 LOC of custom code with comparable or better behavior (hishel for HTTP cache, stdlib `RotatingFileHandler` for NDJSON rotation, trafilatura's bundled metadata for the htmldate + custom OG/JSON-LD path, purgatory for proxy quarantine state).

And the orchestrator (`fetcher.py`, 678 LOC) carries internal smells we keep flagging but never fix — `tier_extras: dict[str, Any]` as a typed hole, two near-duplicate archive-dispatch blocks, decimal "Phase 4.25" comments, slippery `tier_used: str` identity.

Doing all three together as one tracked change ensures the diffs compose: the a2kit migration replaces the lifecycle scaffolding the OSS adoption would otherwise have to re-route around, and the internal cleanup uses the typed abstractions both phases unblock. Total target: ~4448 → ~3600 LOC, two new internal workspace packages (`proxy-pool`, `browser-pool`), one fewer top-level dep (htmldate out, hishel in is net zero).

## What Changes

**Phase A — a2kit v0.23 → v0.26 migration.** **BREAKING** at the framework boundary, no a2web public API change.

- Replace `register_state` + 3× `ensure_X` + `_atexit_close` + `bootstrap_state_for_test` with `app.singleton(AppState, factory=build_state)` + `@app.on_startup` + `@app.on_shutdown`.
- Delete `events/bus.py`, `events/sinks.py.mcp_progress_sink`, `_ProgressCtx` Protocol; route OTel through `app.ldd.add_sink(otel_sink)` (~15 LOC, one file).
- Migrate orchestrator emissions from `EventBus.publish(...)` to `a2kit.ldd.event(ctx, ...)` (free function).
- Add MCP tool annotations to `@a2kit.read()`: `idempotent=True, open_world=True, title="Fetch Web Page"`, plus `Surface.ALL` per v0.26's lint rule.
- Add `a2kit.Param(description=...)` to direct kwargs on the `fetch` tool.
- Rewrite tool docstring per the documented contract (first-line short summary + multi-paragraph body; markdown stripped on CLI, intact on MCP).
- Add `@app.health_check` for sqlite + browser_pool state.
- Rewire 30+ tests: integration tests move to `a2kit.testing.client(app)` invocation; `test_app_state.py` drops async-resolve contortions in favor of `Container.resolve_sync` / `a2kit.testing.peek`; conftest drops REGISTRY monkey-patching in favor of `app.provide(...)` overrides.
- Add new tests previously impossible: `test_router_dispatch.py`, `test_health.py`, `test_lifecycle.py`.
- Add `TierHeartbeat` typed event emitted from inside slow tiers (browser tier 2s interval, archive tier per hedged-request boundary) — closes the "silent until timeout" diagnostic blind spot.
- Bump `pyproject.toml` a2kit pin to v0.26.0 (consider PyPI install if published).

**Phase B — OSS adoption.** **STATUS: SHIPPED with 4 of 5 candidate swaps deferred.** See `retrospective.md` for the why; BACKLOG.md tracks each deferred item.

What landed:
- Consolidated extraction into trafilatura — `extract_metadata()` provides title + author + date in one pass. Removed `extract/htmldate_ext.py` (replaced by trafilatura's bundled date detection) and the `htmldate` top-level dep.
- Deleted `extract/pruning_filter.py` (`fit-md`) entirely. Validation gate ran every existing fit-md fixture through `trafilatura.extract(..., include_comments=False, include_tables=False)`; 0/4 fixtures regressed by >20%. `FetchResponse.fit_md` preserved as response field but now equals `content_md`.

What was deferred (each with architectural reason in BACKLOG.md):
- `hishel` HTTP cache adoption — API requires owning the HTTP transport; would force restructuring every tier rather than a thin shim.
- `aiometer.run_any` for hedged archive race — "first result" semantics ≠ "first success" we need; if Wayback returns None we want to keep waiting for archive.ph.
- `purgatory` for proxy quarantine — sync API mismatch; library swap would force ProxyPool async, propagating to the orchestrator.
- stdlib `RotatingFileHandler` for NDJSON log — sync handler wrapped in `asyncio.to_thread` adds a thread hop per write and worse async semantics than our existing `aiofiles`-based writer.

`extract/metadata.py` (OG/Twitter/JSON-LD parser) **kept** — trafilatura doesn't expose the raw `twitter.*` / `jsonld[0].*` keys our existing tests assert on.

Net dep change: `-htmldate`, no additions. `aiosqlite` stays (hishel deferral means we still own the sqlite cache).

Net LOC: **-180 LOC** (130 fit-md, 50 metadata path consolidation), against the original `~510 LOC` target. The miss is documented honestly rather than swept under a "deferred" carpet.

**Phase C — Internal magic removal.** Refactor only, no behavior change.

- Replace `tier_extras: dict[str, Any]` with typed fields on `TierResult` (or a sub-dataclass `TierExtras`); drop string-key reads in orchestrator.
- Lift the two archive-dispatch blocks in `fetcher.py` (after-tier and after-gate) into one `_dispatch_archive(...)` helper.
- Replace decimal "Phase 4.25" comments with named phase functions (`_phase_extract`, `_phase_gate`, `_phase_escalate`, etc.).
- Unify `tier_used: str` identity rule — single function decides what string lands in `FetchResponse.tier`, no more multi-branch construction.
- Rename `archive` and `browser` tiers conceptually: keep as Tiers in REGISTRY but remove the "registered but not in TIER_ORDER" footnote by documenting the escalation-dispatch contract explicitly.
- Drop the orchestrator's local `bus` parameter and the `_publish` shim — emissions go directly to a2kit.

**Phase D — Workspace packaging.** Layout change only, no behavior change.

- Convert repo to uv workspace; introduce **three** `packages/` with their own `pyproject.toml`, `src/`, `tests/`:
  - `packages/proxy-pool/` (host-glob × tier-rule routing + purgatory-backed quarantine)
  - `packages/browser-pool/` (Camoufox/Playwright lifecycle with per-host context + LRU + idle eviction)
  - `packages/block-detector/` (web anti-bot detection: Cloudflare, Anubis, Turnstile, Akamai BMP, paywall, length-floor)
- Move `src/a2web/proxy/*` → `packages/proxy-pool/src/proxy_pool/`; move `src/a2web/browser/*` → `packages/browser-pool/src/browser_pool/`; move `src/a2web/gate/block_detector.py` → `packages/block-detector/src/block_detector/`.
- Each package defines its own narrow types (no import of `a2web.Verdict` etc.); a2web wraps with adapters in `src/a2web/proxy/`, `src/a2web/browser/`, `src/a2web/gate/`.
- a2web's `pyproject.toml` declares all three as workspace deps.
- `make check` rewired to run per-package + a2web; CI matrix updated.
- Research-confirmed: `fit-md` is NOT packaged (it's deleted entirely in Phase B); `cache-shim`, `hedged-request`, `ndjson-log`, `event-bus` are NOT packaged (each fails the "useful in other projects" + "non-trivial code" test post-Phase-B simplifications).

## Capabilities

### New Capabilities

- `lifecycle`: a2kit lifecycle hook integration — replaces the v0.23 `atexit` + lazy-`ensure_X` workaround pattern with `@app.on_startup` / `@app.on_shutdown` + `app.singleton(AppState, factory=...)`. Owns: startup resource opening (sqlite, proxy pool), shutdown resource closing (sqlite, browser pool if launched), health-check registration.

- `event-streaming`: a2kit ldd-sink integration — replaces the internal `EventBus` + sinks pattern. Owns: orchestrator emission via `a2kit.ldd.event(ctx, ...)`, OTel sink registered via `app.ldd.add_sink(...)`, `TierHeartbeat` events from slow tiers, the typed event registry for `TierStarted/TierEnded/StageStarted/StageEnded` payloads.

- `oss-cache`: hishel-backed HTTP cache — replaces the `cache/sqlite_cache.py` hand-rolled etag/last-modified/304/profile-hash logic. Owns: cache lookup/store via hishel `Controller`+`SQLiteStorage`, the curl_cffi response shim, the bypass list, content-type-driven TTL.

- `oss-extraction`: trafilatura bundled-metadata extraction — replaces `extract/htmldate_ext.py` and `extract/metadata.py`. Owns: single-call extraction of body + title + byline + headings + publish date + OG/JSON-LD metadata.

- `oss-log-writer`: stdlib `RotatingFileHandler` + gzip rotator integration — replaces hand-rolled NDJSON writer. Owns: NDJSON file rotation, gzip on rollover, structlog `JSONRenderer` formatter wiring.

- `oss-proxy-quarantine`: purgatory-backed proxy health state — replaces the 3-fail/600s in-memory state machine. Owns: per-proxy circuit breakers, optional disk persistence path.

- `tier-extras-typed`: typed `TierResult` extras — replaces `tier_extras: dict[str, Any]`. Owns: typed fields for `pre_rendered`, `from_archive`, `snapshot_age_days`, `operator_hint`, `no_match`, `skipped`, `handler_name`, `js_executed`.

- `escalation-dispatch`: explicit out-of-band tier dispatch contract — formalizes the "in REGISTRY but not in TIER_ORDER" rule. Owns: `archive` and `browser` dispatch semantics, the `_dispatch_archive(...)` helper, per-fetch escalation caps (`url_rewrites`, `archive_dispatches`, `browser_dispatches`).

- `workspace-packages`: uv workspace layout — introduces `packages/proxy-pool/`, `packages/browser-pool/`, and `packages/block-detector/` as internal libraries with their own pyproject + tests + types. Owns: package boundary rules, adapter contract back to a2web.

### Modified Capabilities

- `app-composition`: composition root rewires from `register_state(...)` closure to `app.singleton(AppState, factory=build_state)` + lifecycle decorators. Health-check decorator added. Tool decorator gains MCP annotations (`idempotent`, `open_world`, `title`, `Surface.ALL`) and `Param` descriptions.

- `app-state`: `AppState` shrinks — `sqlite_lock`, `browser_lock`, `proxy_lock` deleted; `sqlite` and `proxy_pool` become non-Optional (opened in startup); `browser_pool` stays `Optional` (lazy, optional dep). Test helpers `bootstrap_state_for_test` / `teardown_state_for_test` deleted.

- `streaming-progress`: drops the internal `EventBus` + `MemoryObjectStream` fanout; orchestrator emits directly via `a2kit.ldd.event(ctx, ...)`. OTel sink registered via `app.ldd.add_sink(...)`. The MCP progress sink is gone (a2kit owns the bridge). `TierHeartbeat` events added from inside browser tier (2s interval) and archive tier (per hedged request).

- `cache`: backing store + control logic replaced by hishel; behavior is RFC 9111 (a strict-superset of the hand-rolled etag/last-modified semantics for typical web traffic). The `cache: CacheState` field on `FetchResponse` stays; the `profile_hash` logic and `_ttl_for` heuristic are deleted (hishel's directives replace them).

- `request-log`: writer + rotation replaced by stdlib `RotatingFileHandler` + gzip rotator callback. The record schema stays unchanged; only the writer implementation moves.

- `extraction`: collapses three modules to one trafilatura call. `htmldate` dep removed. Metadata dict still exposed on `FetchResponse.meta`; populated from trafilatura's metadata block.

- `proxy-pool`: quarantine state machine swapped for `purgatory.AsyncCircuitBreakerFactory`. Routing/policy logic (host-glob × tier rules × `${ENV}`) stays custom. Module moves to `packages/proxy-pool/` workspace package.

- `browser-tier`: module moves to `packages/browser-pool/` workspace package. No behavior change.

- `tier-pipeline`: orchestrator (`fetcher.py`) refactored — typed `TierResult` (no more `tier_extras` dict), single `_dispatch_archive(...)` helper (replaces two duplicated blocks), named phase functions (replaces "Phase 4.25" comments), single `tier_used` identity rule.

- `site-handlers`: minor — handlers update their typed return shape to match new `TierResult` fields (no more `tier_extras["pre_rendered"] = {...}`; explicit `pre_rendered=Rendered(...)` instead).

## Impact

**Affected modules.** `src/a2web/` — every file touched. Heaviest: `state.py` (rewrite), `fetcher.py` (refactor + emission migration), `routers.py` (tool decorator + docstring), `events/` (delete most), `cache/` (replace with shim), `log/` (replace with stdlib glue), `extract/` (collapse three modules to one), `proxy/` (move to package + purgatory swap), `browser/` (move to package).

**Affected tests.** `tests/conftest.py` (drop REGISTRY monkey-patching), `tests/test_app_state.py` (drop async-resolve contortions), `tests/test_fetcher.py` and ~10 other integration tests (move to `a2kit.testing.client`), `tests/test_cache.py` (rewrite against hishel), `tests/test_log_*` (rewrite against stdlib glue). New: `test_router_dispatch.py`, `test_health.py`, `test_lifecycle.py`, `test_tier_heartbeat.py`.

**APIs.**
- Tool wire surface unchanged (`fetch(url) -> FetchResponse`) — agents and existing MCP clients see no change.
- `FetchResponse` shape unchanged at field level; semantics of `cache` field tightens to RFC 9111 (hishel-driven).
- Internal: `EventBus`, `register_state`, `ensure_*`, `bootstrap_state_for_test`, `teardown_state_for_test`, `compute_profile_hash`, `_ttl_for`, `is_live_only` all deleted.

**Dependencies (Phase A+B actual).**
- `a2kit>=0.23,<1` → `a2kit>=0.26,<1` (BREAKING migration). ✅ shipped
- `htmldate` removed. ✅ shipped
- `aiosqlite` — stays (hishel deferral; we still own the sqlite cache).
- `hishel` — NOT added (deferred to BACKLOG; see retrospective).
- `aiometer` — NOT added (deferred to BACKLOG; semantic mismatch).
- `purgatory` — already pinned; usage unchanged (deferred broadening to PR7e).
- `trafilatura` — already pinned; usage broadened to include `extract_metadata()` for title/author/date in one pass. ✅ shipped

**Systems.**
- Workspace layout: monorepo becomes uv workspace with two internal packages.
- `make check` rewired to run lint+ty+test per-package.
- CI: matrix unchanged (still one job) but invokes the workspace-aware command.
- Cache file format changes (hishel's SQLite schema differs from ours) — existing `~/.a2web/cache.sqlite` files are abandoned; users get a fresh cache on first post-upgrade run. Acceptable since cache is non-authoritative.

**Sequencing.** Phase A first as a standalone PR (clean diff, framework-only). Phase B next as a single PR (OSS adoption arc; cache breaking change shipped here). Phase C as a standalone PR (refactor only, no dep change). Phase D last, after the other phases have settled, as a layout-only PR. The four PRs are independently reviewable.

**Backlog deferrals.** Update `BACKLOG.md`:
- Remove: nothing (no v0.1 items shipped by this change).
- Add: chunked `content_md` streaming response (deferred until human-UI consumer emerges; confirmed with a2kit dev that LLM/CLI consumers buffer anyway).

**Risk.** Highest risk is the hishel shim — curl_cffi's response shape differs from httpcore's, and hishel's sans-I/O Controller expects an httpcore-compatible interface. Mitigation: Phase B starts with a hishel-only spike PR (just the shim, no migration) to verify the seam before broader work. If the shim exceeds ~80 LOC or has unsolved edge cases, defer hishel adoption to a v0.2 follow-up and ship only NDJSON + trafilatura + purgatory in Phase B.
