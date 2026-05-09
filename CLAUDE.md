# a2web — Agent-to-Web

CLI and MCP server for AI agents to fetch web content adaptively. Built on `a2kit` (which handles MCP, CLI, DI, ConnectionStore, formatter, LDD, schema, testing).

Design lives in `~/Documents/Knowledge/Projects/120-a2web/`. Read `handover.md` first.

## Architecture (a2kit-mediated)

a2kit owns: `App`, `Router`, `ToolContext` (4-channel logging/progress/events/reports), formatter (TOON), schema discovery, MCP server build, CLI build, testing fixtures, LDD kill-switches, lint. a2web does NOT use `connections_cli` / `ConnectionConfig` — see `settings.py` below.

a2web owns the web-fetching domain:

- `src/a2web/settings.py` — `AppSettings(BaseSettings)` loaded from env (`A2WEB_*`) + optional YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, `jina_key` (env-only secret). No paid-tier keys in v0.1.
- `src/a2web/server.py` — `a2kit.App` composition; `main()`. No connections CLI.
- `src/a2web/routers.py` — `WebRouter` (single tool: `fetch(url)`). CLI surface: `a2web web fetch --url=...`.
- `src/a2web/state.py` — `AppState` `@dataclass(slots=True)`: settings + typed `Optional` placeholders for sqlite, log_writer, proxy_pool, breakers, browser_pool. Per-App singleton via `register_state(app, *, settings=None)` closure (NOT process-wide `lru_cache` — would break the two-App canary). Tools resolve via `state: AppState` kwarg.
- `src/a2web/models.py` — `FetchResponse`, `Diagnostic`, `Verdict` (closed enum), `Heading`, `Link`, `OperatorHint`, `TokenCounts`. All at module scope (a2kit antipattern #2). pydantic at boundaries; `dataclass(slots=True)` internally for the pipeline.
- `src/a2web/fetcher.py` — orchestrator (`select_next` policy + lifecycle loop, ≤400 lines)
- `src/a2web/tiers/` — Strategy + Registry: `raw.py` (curl_cffi), `jina.py`, `archive.py` (CDX + archive.ph hedged), `browser.py` (Camoufox lazy), `paid.py` (Firecrawl env-gated)
- `src/a2web/handlers/` — site-specific tier-0: `reddit.py` (`.json?limit=500`), `hn.py` (Algolia), `youtube.py`, `arxiv.py`, `github.py`, `wikipedia.py`, `substack.py`, `twitter.py`
- `src/a2web/extract/` — `trafilatura_ext.py`, `htmldate_ext.py`, `metadata.py` (OG/JSON-LD), `pruning_filter.py` (fit_md), `readability_fallback.py`. Sync; pipeline wrapped in `asyncio.to_thread` once.
- `src/a2web/gate/` — `block_detector.py` (closed-enum verdicts), `quality_score.py`. Pure functions, unit-testable without I/O.
- `src/a2web/cache/` — `sqlite_cache.py` (etag/last-modified, content-hash dedup, conditional GET).
- `src/a2web/proxy/` — `pool.py` (per-host/per-tier routing, health-check loop), `policy.py` (route table parser).
- `src/a2web/browser/` — Camoufox pool (lazy, lifespan-managed, sticky-per-host).
- `src/a2web/actions/` — `playbook.py` (autonomous-action table: paywall→archive, arxiv-pdf→html, etc.)
- `src/a2web/log/` — NDJSON request log with rotation; `a2web logs tail/grep/stats/replay`.

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

## Ask First

- Before changing tool signatures (breaking for MCP clients).
- Before adding new top-level dependencies.
- Before changing the response envelope shape (breaking for parsers).
- Before introducing a new tier or handler that doesn't fit the existing Strategy + Registry.
