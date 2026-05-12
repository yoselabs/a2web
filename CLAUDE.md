# a2web — Agent-to-Web

CLI and MCP server for AI agents to fetch web content adaptively. Built on `a2kit` v0.26+ (which handles MCP, CLI, DI, lifecycle, formatter, LDD typed events, schema discovery, in-process testing).

Design lives in `~/Documents/Knowledge/Projects/120-a2web/`. Read `handover.md` first. Migration story for v0.2 lives in `openspec/changes/archive/2026-05-11-migrate-to-a2kit-v026-and-simplify/` and `docs/history/A2KIT_FEEDBACK.md`.

## Architecture (a2kit v0.26 mediated)

a2kit (v0.27+) owns: `App`, `Router`, `ToolContext`, `app.singleton(T, factory)` (sync factory), DI-aware `@app.on_startup` / `@app.on_shutdown` / `@app.health_check` (handlers take typed kwargs like `state: AppState`), `app.ldd.events.register(T)` + typed `a2kit.ldd.event(ctx, instance)` emit, `a2kit.ldd.report(...)`, `app.ldd.add_sink(sink)`, in-process `a2kit.testing.client(app)` + `a2kit.testing.peek` + `a2kit.testing.null_context()` for direct phase tests, formatter (type-driven JSON/TSV/page-tsv routing), `a2kit.Param` for arg metadata, MCP server build, CLI build, lint.

a2web owns the web-fetching domain. Composition is **imperative** (per a2kit v0.26 README) — no fluent builder chain:

- `src/a2web/settings.py` — `AppSettings(BaseSettings)` from env (`A2WEB_*`) + optional YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, `jina_key` (env-only secret). `${ENV_VAR}` references inside YAML resolve at load time.
- `src/a2web/server.py` — imperative `a2kit.App` composition; registers `AppState` singleton, typed event payloads, OTel sink. Lifecycle hooks are DI-aware (take `state: AppState` directly, no container ceremony). `@app.on_startup` warms `state.sqlite._ensure()` for fail-fast config errors; `@app.on_shutdown` closes every Resource idempotently; `@app.health_check` probes sqlite. `main()` dispatches to MCP/CLI.
- `src/a2web/routers.py` — `WebRouter` exposes one tool `fetch(url)` via `@a2kit.read(idempotent=True, open_world=True, ...)`. CLI surface: `a2web web fetch --url=...`. Tool args use `Annotated[str, a2kit.Param(description=...)]`.
- `src/a2web/state.py` — `AppState` `@dataclass(slots=True)` with **every field non-Optional**. Resource pattern (a2kit v0.27 canonical) for the async-init ones: `SqliteResource`, `BrowserPool`, `LlmExtractorResource` each own their own `asyncio.Lock` and lazy `_ensure()` method. Locks never leak to state. `build_state(settings)` is sync (a2kit hard requirement) and constructs every Resource cheaply; real I/O happens on first `_ensure()`. Tests call `build_state(settings=AppSettings(...))` to get a complete AppState.
- `src/a2web/models.py` — `FetchResponse`, `Diagnostic`, `Verdict`, `Heading`, `Link`, `OperatorHint`, `TokenCounts`. All at module scope (a2kit antipattern #2). pydantic at boundaries; `dataclass(slots=True)` internally.
- `src/a2web/fetcher.py` — orchestrator. `_run_pipeline` is a 12-line coordinator calling six named phases: `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate` (which calls `_escalate_browser` / `_dispatch_archive`), `_phase_cache_write`. State flows through a single `FetchContext` `dataclass(slots=True)` instead of 20+ parameters. Tier loop body is split into named helpers (`_install_won_tier`, `_install_archive_payload`, `_apply_after_tier_action` returning `_AfterTier` enum). Escalators share `_emit_tier_started` / `_emit_tier_ended` + `_regate_after_escalation` helpers.
- `src/a2web/tiers/` — Strategy + Registry. `raw.py` (curl_cffi), `jina.py` (r.jina.ai reader), `archive.py` (Wayback CDX + archive.ph hedged via anyio task group), `browser.py` (Camoufox via `BrowserPool`), `paid.py` (Firecrawl env-gated). `TIER_ORDER = ("site_handler", "raw", "jina")`; archive + browser are in REGISTRY but **not** in TIER_ORDER — orchestrator dispatches them out-of-band (archive on playbook `RetryViaArchive`; browser on gate `suggested_tier == "browser"`, capped at 1/fetch). **`TierResult` is a typed dataclass with named fields** (`pre_rendered: Rendered | None`, `from_archive`, `from_browser`, `js_executed`, `browser_wall_ms`, `browser_bytes`, `snapshot_age_days`, `operator_hint`, `no_match`, `skipped`, `handler_name`, `conditional_hit`, `archive_source`) — the `tier_extras: dict[str, Any]` bag is gone.
- `src/a2web/handlers/` — site-specific tier-0 (Handler protocol = Tier + `matches(url)`). `reddit.py`, `hn.py`, `arxiv.py`, `wikipedia.py`, `github.py` (optional `A2WEB_GITHUB_TOKEN` raises rate limit 60→5000/hr). Handlers populate `TierResult.pre_rendered: Rendered` (typed: `content_md`, `title`, `byline`, `headings`) so the orchestrator skips trafilatura/metadata; gate still runs. No-match URLs return `TierResult(no_match=True)` and are skipped silently.
- `src/a2web/domain.py` — domain-coupled glue. Pure functions reading `AppSettings` or models but too small for their own files: `compute_profile_hash`, `is_live_only`, `log_from_response`. Lives at top level because the previous per-domain seam directories were nuked.
- `src/a2web/events/` — `types.py` (typed event payloads: `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, `TierHeartbeat`), `sinks.py` (`otel_sink(emission: LddEmission)` — one span per `*Ended` event, no-op when SDK absent). a2kit owns the bus; the custom `MemoryObjectStream` fan-out is gone. Emit via `a2kit.ldd.event(StageStarted(...))` from anywhere in the pipeline; `app.ldd.add_sink(otel_sink)` subscribes the OTel half.
- `src/a2web/llm_resource.py` — `LlmExtractorResource`. AppSettings-aware provider selection (auto/anthropic/claude-code), plumbs `SqliteResource` into `ExtractionCache`, gates construction on the optional `[llm]` install extra. Domain-coupled — stays out of `packages/`.
- `src/a2web/llm_eval/` — eval harness (`EvalSuite`, `Judge` wrapper, `WebFetchBaseline` / `A2WebDetail` / `A2WebExtract` systems). Domain-coupled — imports `AppSettings`, `FetchResponse`, `build_state`.
- `src/a2web/packages/` — in-tree microsofware. Modules under here MUST NOT import from `a2web.<domain>`. Boundary types are owned by the package; domain-coupled wiring lives in `domain.py` / `llm_resource.py`. Current packages (all flat `.py` files except `llm_extract/`): `browser_pool`, `block_detector`, `http_cache`, `proxy_routing`, `content_extract`, `llm_extract/` (folder — multi-author surface with `extractor`, `judge`, `cache`, `prompts`, `errors`, and `providers/{anthropic,base,claude_code}`). The `tests/test_packages_independence.py` invariant walks every `.py` under `packages/` and asserts zero domain imports.
- `src/a2web/actions/` — `playbook.py` (pure deterministic `next_action_after_gate` / `next_action_after_tier`). Per-fetch counters in `FetchContext`: `url_rewrites`, `archive_dispatches`, `browser_dispatches`.

## Testing

a2kit's in-process test client is the default: `client = a2kit.testing.client(app); await client.call("WebRouter.fetch", url=...)`. Use `a2kit.testing.peek(app)` for resource inspection. Unit tests construct `FetchContext` directly and invoke a single phase function in isolation.

## Dev Commands

- Full gate: `make check` (lint + ty + test, coverage ≥85%)
- Lint: `make lint`; auto-fix: `make fix`
- Type check: `make ty` (Astral `ty`)
- Tests: `make test` (pytest, asyncio_mode=auto)
- Local MCP: `make dev`
- Bootstrap: `make bootstrap` (uv sync --all-extras)

## Conventions

- `dataclass(slots=True)` for internal pipeline objects; pydantic only at API boundaries.
- `asyncio.to_thread` chokepoint per sync module (trafilatura, sqlite). Ruff `ASYNC100/210/230` enforces.
- All shared state hangs off `AppState`; tools resolve via `state: AppState` kwarg (a2kit DI). No globals, no module-level lazy caches.
- Lifecycle: `@app.on_startup` opens, `@app.on_shutdown` closes. No `atexit` hooks.
- Events: emit via `a2kit.ldd.event(PayloadType(...))`; subscribe additional consumers via `app.ldd.add_sink(...)`.
- Structured logging via `structlog` + `bind_contextvars`; OTel `trace_id` is the correlation ID.
- `purgatory` for circuit breakers (per-host, per-proxy, global).
- Closed-enum verdicts for diagnostics.
- `fmt_dur(ms)` helper for every duration string.
- Don't return `-> str` from a tool. Return dict / pydantic model.
- All return-type pydantic models at module scope.

## Never

- Never commit credentials. Secrets are env-only (`A2WEB_*`).
- Never bypass the quality gate when writing to cache (block pages must never enter cache).
- Never silently drop a fetch — `status: failed` + populated `diagnostics` + `narrative` + `operator_hints` is the floor.
- Never retry the whole flow — retries live at one of 5 specific layers (connection / HTTP / proxy / tier / handler) with circuit breakers.
- Never add `print()` or sync I/O in async paths.
- Never reintroduce `tier_extras: dict[str, Any]` — add a typed field on `TierResult` instead.
- Never reintroduce a module-level `atexit` resource-close hook — use `@app.on_shutdown`.
- Never import from `a2web.<domain>` inside `src/a2web/packages/`. Boundary types are package-owned; domain wiring lives at the a2web seam. `tests/test_packages_independence.py` fails CI on drift.

## Backlog

`BACKLOG.md` tracks deferred work (Phase D workspace packaging, OSS swaps that turned out to be wrong fit, post-v0.1 features). CHANGELOG.md is the shipped record.

## Ask First

- Before changing tool signatures (breaking for MCP clients).
- Before adding new top-level dependencies.
- Before changing the response envelope shape (breaking for parsers).
- Before introducing a new tier or handler that doesn't fit Strategy + Registry.
- Before reintroducing a `dict[str, Any]` bag on a typed pipeline object.
- Before promoting a new module to `packages/` — boundary types need design, and the seam may need conversion logic.
