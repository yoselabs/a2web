# Implementation Tasks

## 1. Lazy sqlite singleton

- [x] 1.1 Add `_sqlite_lock: asyncio.Lock | None` field to `AppState`; initialize in `register_state`
- [x] 1.2 Add `ensure_sqlite(state) -> aiosqlite.Connection` in `state.py` (lazy open under lock, cache on `state.sqlite`)
- [x] 1.3 Register `atexit` hook in `register_state` that closes `state.sqlite` on a fresh loop, swallowing errors
- [x] 1.4 Add `bootstrap_state_for_test(settings=None)` and `teardown_state_for_test(state)` helpers
- [x] 1.5 Drop per-fetch `aiosqlite.connect` from `src/a2web/fetcher.py`; route through `ensure_sqlite(state)`
- [x] 1.6 Update existing tests to use `bootstrap_state_for_test` / `teardown_state_for_test`

## 2. OTel sink

- [x] 2.1 Add `opentelemetry-api` to optional dep group `otel` in `pyproject.toml`; add to dev deps so CI exercises the sink
- [x] 2.2 Implement `otel_sink(recv)` in `src/a2web/events/sinks.py` with lazy import + drain-on-missing
- [x] 2.3 Update `WebRouter.fetch` to subscribe a second receiver and start `otel_sink` under the same task group
- [x] 2.4 Test: stub tracer captures one span per phase boundary with correct attrs
- [x] 2.5 Test: with OTel module monkeypatched to None, sink still drains the stream

## 3. Jina tier

- [x] 3.1 Add `jina_deny_hosts: list[str] = []` to `AppSettings`
- [x] 3.2 Implement `JinaTier` in `src/a2web/tiers/jina.py` (httpx async client, bearer-optional, deny-list short-circuit, `pre_rendered` payload)
- [x] 3.3 Register in `REGISTRY` and extend `TIER_ORDER` to `("site_handler", "raw", "jina")`
- [x] 3.4 Tests: free-tier (no auth header), authorized (bearer present), deny-list short-circuit, pre-rendered path through orchestrator

## 4. Gate & polish

- [x] 4.1 `make lint` clean (no `ASYNC100/210/230` violations, zero `# ty: ignore`)
- [x] 4.2 `make ty` clean
- [x] 4.3 `make test` green, coverage ≥85%
- [x] 4.4 Live demo: `a2web web fetch --url=https://example.com` end-to-end (lifespan logs sqlite open once)
- [x] 4.5 Update `CLAUDE.md` architecture notes (lifespan ownership, jina-deny-list, otel-sink)
- [x] 4.6 Commit `PR7a: lifespan + otel sink + jina tier`
- [x] 4.7 Archive change via `openspec archive pr7a-lifespan-otel-jina`
