## Why

PR3 deferred sqlite/breaker/log lifecycle to "per-fetch" because we lacked a lifespan hook — every fetch opens & closes its own sqlite connection, which is wasteful and prevents WAL-mode reuse. PR6 shipped a streaming event bus but only one sink (MCP progress); OTel is needed for cross-fetch correlation in real traffic. We also need at least one *post-raw* tier before the cascade is meaningful — Jina is the cheapest one to build (single HTTP call, env-gated key, no proxy concerns).

## What Changes

- App lifespan: a2kit `App.lifespan(...)` hook opens sqlite once, mounts it on `AppState`, closes on shutdown. `LogWriter` and breaker factory move from per-call construction to lifespan-owned singletons.
- Orchestrator stops calling `open_sqlite_with_schema` on every fetch — reads `state.sqlite` directly. **BREAKING** for tests that constructed `AppState` without going through `register_state` + lifespan; helper `bootstrap_state_for_test()` lands alongside.
- `events/sinks.py` adds `otel_sink(tracer, recv)` — emits one OTel span per `TierEnded`/`StageEnded` with `t_ms`, `verdict`, `dur_ms` attrs. Lazy-imports `opentelemetry.trace`; no-ops if OTel SDK absent.
- `tiers/jina.py`: new `JinaTier`. Calls `https://r.jina.ai/{url}` with `X-Return-Format: markdown`, `Authorization: Bearer ${A2WEB_JINA_KEY}` if set (free tier without). Result populates `tier_extras["pre_rendered"]` (markdown body), bypassing trafilatura — same path Reddit/HN handlers use.
- `TIER_ORDER` becomes `("site_handler", "raw", "jina")`. Jina is invoked when raw lands a non-`ok` verdict (block/paywall/length_floor) **and** the URL isn't on a Jina deny-list (gov, login walls — config field).
- `WebRouter.fetch` attaches `otel_sink` alongside `mcp_progress_sink` when OTel SDK importable; both sinks get their own subscription.

## Capabilities

### New Capabilities
- `lifespan`: app-level singletons (sqlite, log writer, breaker factory) opened on startup, closed on shutdown
- `otel-sink`: OTel span emission per phase boundary, subscribed to the same event bus
- `jina-tier`: Jina r.jina.ai reader as a post-raw fallback tier

### Modified Capabilities
- `app-state`: `AppState.sqlite` becomes non-Optional after lifespan boot; `bootstrap_state_for_test()` helper added
- `tier-pipeline`: `TIER_ORDER` extended; selection skips Jina on deny-list

## Impact

- `pyproject.toml`: optional `opentelemetry-api` dep group `otel`; runtime import-guarded
- `src/a2web/server.py`: lifespan registration
- `src/a2web/state.py`: lifespan-aware singleton wiring; test helper
- `src/a2web/fetcher.py`: drop per-fetch sqlite open
- `src/a2web/events/sinks.py`: `otel_sink` added
- `src/a2web/tiers/jina.py`: new file
- `src/a2web/tiers/__init__.py`: registry update
- `src/a2web/settings.py`: `jina_deny_hosts: list[str]`
- Tests: lifespan harness, otel sink (with stub tracer), jina tier (with httpx mock)
