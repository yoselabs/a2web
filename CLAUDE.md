# a2web — Agent-to-Web

CLI and MCP server for AI agents to fetch web content adaptively. Built on `a2kit` (which handles MCP, CLI, DI, ConnectionStore, formatter, LDD, schema, testing).

Design lives in `~/Documents/Knowledge/Projects/120-a2web/`. Read `handover.md` first.

## Architecture (a2kit-mediated)

a2kit owns: `App`, `Router`, `ToolContext` (4-channel logging/progress/events/reports), formatter (TOON), schema discovery, MCP server build, CLI build, testing fixtures, LDD kill-switches, lint. a2web does NOT use `connections_cli` / `ConnectionConfig` — see `settings.py` below.

a2web owns the web-fetching domain:

- `src/a2web/settings.py` — `AppSettings(BaseSettings)` loaded from env (`A2WEB_*`) + optional YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, `jina_key` (env-only secret). No paid-tier keys in v0.1.
- `src/a2web/server.py` — `a2kit.App` composition; `main()`. No connections CLI.
- `src/a2web/routers.py` — `WebRouter` (single tool: `fetch(url)`). CLI surface: `a2web web fetch --url=...`.
- `src/a2web/state.py` — `AppState` `@dataclass(slots=True)`: settings + typed `Optional` placeholders for sqlite, log_writer, proxy_pool, breakers, browser_pool. Per-App singleton via `register_state(app, *, settings=None)` closure (NOT process-wide `lru_cache` — would break the two-App canary). Tools resolve via `state: AppState` kwarg. PR7a: sqlite is opened **lazily** by `ensure_sqlite(state)` on first fetch under an `asyncio.Lock`, cached on `state.sqlite`, closed by an `atexit` hook on a fresh loop. a2kit v0.23 has no lifespan hook to forward FastMCP's `lifespan=`, so this lazy+atexit pattern owns the lifecycle for both CLI and MCP entry paths. Tests use `bootstrap_state_for_test()` / `teardown_state_for_test()`.
- `src/a2web/models.py` — `FetchResponse`, `Diagnostic`, `Verdict` (closed enum), `Heading`, `Link`, `OperatorHint`, `TokenCounts`. All at module scope (a2kit antipattern #2). pydantic at boundaries; `dataclass(slots=True)` internally for the pipeline.
- `src/a2web/fetcher.py` — orchestrator (`select_next` policy + lifecycle loop, ≤400 lines)
- `src/a2web/tiers/` — Strategy + Registry: `raw.py` (curl_cffi), `jina.py` (PR7a, r.jina.ai reader, bearer-optional, deny-list short-circuit), `archive.py` (PR7b, Wayback CDX + archive.ph hedged via anyio task group, Wayback chrome stripped before trafilatura), `browser.py` (PR7c, Camoufox lazy via `BrowserPool`, page-per-fetch, persistent per-host context, 30s page budget), `paid.py` (Firecrawl env-gated). `TIER_ORDER = ("site_handler", "raw", "jina")`; archive **and** browser are in REGISTRY but **not** in TIER_ORDER — orchestrator dispatches them out-of-band (archive on playbook `RetryViaArchive`; browser on gate `suggested_tier == "browser"`, capped at 1 dispatch/fetch). Archive results carry `tier_extras["from_archive"]=True`, skip cache write, and may carry `snapshot_age_days`. Browser results carry `tier_extras["from_browser"]=True` + `js_executed=True` + `browser_wall_ms`/`browser_bytes`; **cache normally** (live page, unlike archive). Camoufox is an optional dep group `[browser]`; missing → graceful `connection_error` + `operator_hints[code=browser_unavailable]`, never a crash.
- `src/a2web/handlers/` — site-specific tier-0 (Handler protocol = Tier + `matches(url)`). PR5 shipped `reddit.py` (`.json?limit=500`), `hn.py` (Algolia). PR8 adds `arxiv.py` (export.arxiv.org Atom), `wikipedia.py` (REST `page/html/<title>` + trafilatura), `github.py` (REST API for repo/issue/pull; optional `A2WEB_GITHUB_TOKEN` raises rate limit 60→5000/hr). PR8 deferred: `youtube.py` (needs browser tier or `yt-dlp` opt-in), `substack.py` (auto-detection complexity; trafilatura already handles articles), `twitter.py` (auth-gated, no clean v0.1 path). The `SiteHandlerTier` dispatcher sits at `tiers/site_handler.py`. Handlers populate `tier_extras["pre_rendered"] = {content_md, title, byline, headings}` so the orchestrator skips trafilatura/htmldate/metadata; the gate still runs on the rendered markdown. No-match URLs return `tier_extras["no_match"]=True` and are skipped silently (no diagnostic row).
- `src/a2web/extract/` — `trafilatura_ext.py`, `htmldate_ext.py`, `metadata.py` (OG/JSON-LD), `pruning_filter.py` (fit_md, in-tree block-density algorithm — no crawl4ai dep). Sync; pipeline wrapped in `asyncio.to_thread` once.
- `src/a2web/events/` — diagnostic event bus (anyio MemoryObjectStream fan-out). One producer (orchestrator), pluggable sinks. PR6 ships `mcp_progress_sink` (forwards events as `ctx.event` + `ctx.report_progress`); PR7a adds `otel_sink` (lazy-imports `opentelemetry.trace`, emits one span per `*Ended` event, drains stream silently when SDK absent). The bus is opt-in via `fetcher.fetch(url, *, state, bus=...)`; without one, behavior is unchanged.
- `src/a2web/gate/` — `block_detector.py` (closed-enum verdicts + `suggested_tier` hint), `quality_score.py`. Pure functions, unit-testable without I/O. PR7c: `GateResult.suggested_tier` carries `"browser"` (anubis/turnstile/akamai_bmp/js_required) or `"tls_impersonate"` (cf_iuam) per engineering.md §2 signal table; orchestrator (not gate) acts on it.
- `src/a2web/cache/` — `sqlite_cache.py` (etag/last-modified, content-hash dedup, conditional GET).
- `src/a2web/proxy/` — PR7d: `policy.py` (pure `resolve_route(host, tier, settings)` → `ResolvedRoute`; first-match-wins, host glob, tier match, AND-composition, `${ENV_VAR}` resolution, explicit `direct`, default-direct fallthrough); `pool.py` (`ProxyPool` with health states alive/quarantined/dead, 3-failure→600s quarantine, `acquire(host, tier)` walks primary+fallback chain, `report(handle, success, ms)`). Lazy via `state.ensure_proxy_pool`. Health is in-memory only (PR7e adds disk persistence + background health-check). No CLI yet (PR7e+). Browser/archive proxy plumbing deferred to PR7e.
- `src/a2web/browser/` — PR7c: `BrowserPool` (Camoufox via playwright async API). Lazy: `state.ensure_browser_pool` opens it under an `asyncio.Lock` on first dispatch; atexit hook closes on a fresh loop (mirrors PR7a sqlite). Persistent contexts keyed by host (cookie jar warm same-host); page-per-fetch (1:1 to avoid state leak); LRU eviction at `browser_max_pool` (default 4); idle eviction at `browser_idle_timeout_s` (default 300s); fire-and-forget eviction tasks tracked in `_eviction_tasks` set so they aren't GC'd mid-close. Settings: `browser_enabled`, `browser_max_pool`, `browser_idle_timeout_s`, `browser_page_budget_s`.
- `src/a2web/actions/` — `playbook.py` (PR7b, autonomous-action table: paywall→archive, block-page→archive, cloudflare-403→archive, arxiv-pdf→abs). Pure deterministic functions: `next_action_after_gate`, `next_action_after_tier`. PR7d closes the after-tier no-op: `RewriteUrl` (cap 1; restarts the tier loop with the new URL, anti-loop) and after-tier `RetryViaArchive` (shares `archive_dispatches` cap of 1 with after-gate — they're mutually exclusive paths to the same archive recovery). Per-fetch counters: `url_rewrites`, `archive_dispatches`, `browser_dispatches`.
- `src/a2web/log/` — NDJSON request log with size-based rotation + gzip on rollover. One record per fetch. Lazy-open writer, best-effort writes (failures append `operator_hints[code=log_write_failed]`, never propagate). No bundled CLI: use `tail`, `grep`, `jq` directly against the NDJSON files. Replay-from-cache (`a2web fetch --replay <ts>`) is deferred — see `BACKLOG.md` (PR10b).

## Dev Commands

- Full gate: `make check` (lint + ty + test)
- Lint: `make lint` (ruff check); auto-fix: `make fix`
- Type check: `make ty` (Astral `ty`)
- Tests: `make test` (pytest, asyncio_mode=auto, coverage ≥85%)
- Local MCP: `make dev`
- Bootstrap: `make bootstrap` (uv sync --all-extras)

## Conventions

- `dataclass(slots=True)` for internal pipeline objects; pydantic only at API boundaries (tool inputs/returns, profile schema).
- `asyncio.to_thread` chokepoint per sync module (trafilatura, sqlite, htmldate). Ruff `ASYNC100/210/230` enforces.
- All shared state hangs off `AppState`; tools resolve via a2kit DI (`store: AppState` kwarg). No globals.
- Structured logging via `structlog` + `bind_contextvars`; OTel `trace_id` is the correlation ID.
- Single `anyio.MemoryObjectStream` as the diagnostic event bus; sinks: OTel events, NDJSON writer, `ctx.event(...)` and `ctx.report_progress(...)`.
- `purgatory` for circuit breakers (per-host, per-proxy, global).
- Closed-enum verdicts for diagnostics (`ok`, `paywall`, `block_page_detected`, `anti_bot:<system>`, `length_floor`, `content_type_mismatch`, `connection_error`, `timeout`, `not_found`, `rate_limited`, `proxy_unavailable`, `other`).
- `fmt_dur(ms)` helper for every duration string. Adaptive: `<1s`→`Xms`, `1-7s`→`X.Xs`, `7-60s`→`Xs`, `≥60s`→`MmSs`.
- Don't return `-> str` from a tool (a2kit antipattern #1). Return dict / pydantic model. Wrap markdown bodies in a typed envelope.
- All return-type pydantic models at module scope (a2kit antipattern #2).

## Never

- Never commit credentials. Secrets (`jina_key`, paid-tier API keys) are env-only via `A2WEB_*` vars — never written to the YAML config. `${ENV_VAR}` references inside the YAML resolve at `AppSettings()` load.
- Never bypass the quality gate when writing to cache (block pages must never enter cache).
- Never silently drop a fetch — `status: failed` + populated `diagnostics` + `narrative` + `operator_hints` is the floor.
- Never retry the whole flow — retries live at one of 5 specific layers (connection / HTTP / proxy / tier / handler) with circuit breakers.
- Never add `print()` or sync I/O in async paths. ASYNC lint catches; CI fails.

## Backlog

`BACKLOG.md` (repo root) tracks deferred work. Every change that defers an item adds it; every change that ships one removes it. CHANGELOG.md is the shipped record; BACKLOG.md is the not-yet record.

## Ask First

- Before changing tool signatures (breaking for MCP clients).
- Before adding new top-level dependencies.
- Before changing the response envelope shape (breaking for parsers).
- Before introducing a new tier or handler that doesn't fit the existing Strategy + Registry.
