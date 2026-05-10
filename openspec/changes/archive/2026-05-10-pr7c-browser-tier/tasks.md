# Implementation Tasks

## 1. Gate signal table (no dependencies)

- [ ] 1.1 Extend `GateResult` in `gate/block_detector.py` with `suggested_tier: str | None = None`
- [ ] 1.2 Add signal→tier mapping table per engineering.md §2 (anubis, turnstile, akamai, cf_managed, js_required, cf_iuam → browser/tls_impersonate)
- [ ] 1.3 Populate `suggested_tier` from current detectors (anubis already detected; extend regexes for turnstile/akamai/cf-mitigated/noscript-shell)
- [ ] 1.4 Tests: each signal produces correct `suggested_tier`; no false positives on legit articles

## 2. Optional dep + state plumbing

- [ ] 2.1 Add `[project.optional-dependencies] browser` in `pyproject.toml` with `camoufox[geoip]`, `playwright`
- [ ] 2.2 Add `browser_enabled`, `browser_max_pool`, `browser_idle_timeout_s`, `browser_page_budget_s` to `AppSettings`
- [ ] 2.3 Add `ensure_browser_pool(state)` async helper in `state.py` (asyncio.Lock-guarded, lazy init)
- [ ] 2.4 Add `_close_browser_pool` atexit hook (fresh-loop pattern from PR7a sqlite)
- [ ] 2.5 Update `bootstrap_state_for_test` / `teardown_state_for_test` to close the pool explicitly
- [ ] 2.6 Tests: lazy init; double-call returns same pool; teardown closes Camoufox cleanly

## 3. Browser pool

- [ ] 3.1 Create `src/a2web/browser/__init__.py` + `pool.py` skeleton
- [ ] 3.2 Implement `BrowserPool` (Camoufox via `playwright.async_api`)
- [ ] 3.3 Persistent contexts keyed by host (LRU at `max_pool`)
- [ ] 3.4 Page-per-fetch, closed after release
- [ ] 3.5 Idle context eviction at `browser_idle_timeout_s`
- [ ] 3.6 Resource budget enforcement: 30s wall + 50MB transferred → page closed, surface `timeout`
- [ ] 3.7 Tests: context reuse same-host; LRU eviction at cap+1; budget enforcement; graceful close

## 4. Browser tier

- [ ] 4.1 Create `src/a2web/tiers/browser.py` skeleton (`name = "browser"`, async fetch, Tier protocol)
- [ ] 4.2 Acquire page via `ensure_browser_pool(state)`; navigate with network-idle wait
- [ ] 4.3 Capture rendered HTML + final URL (post-redirect)
- [ ] 4.4 Trafilatura → markdown inside the tier; populate `tier_extras["pre_rendered"]`
- [ ] 4.5 Set `tier_extras["from_browser"] = True`, `tier_extras["js_executed"] = True`
- [ ] 4.6 Surface `tier_extras["browser_wall_ms"]`, `tier_extras["browser_bytes"]`
- [ ] 4.7 Graceful degradation: `ImportError` on Camoufox → `Verdict.connection_error` + `operator_hints[code=browser_unavailable]`
- [ ] 4.8 Register in `REGISTRY` (NOT in `TIER_ORDER`)
- [ ] 4.9 Tests: happy path against local Anubis fixture; navigation timeout → `timeout`; budget exhaustion; missing Camoufox → graceful

## 5. Orchestrator integration

- [ ] 5.1 Add per-fetch counter `browser_dispatches` to orchestrator stack
- [ ] 5.2 After gate runs, when `gate_result.suggested_tier == "browser"`, dispatch browser tier directly (skip intermediate `TIER_ORDER` slots)
- [ ] 5.3 When `suggested_tier == "tls_impersonate"`, no-op (raw already uses curl_cffi)
- [ ] 5.4 Cap `browser_dispatches` at 1 per fetch
- [ ] 5.5 Browser-rendered results cache normally (unlike archive — `from_browser` is NOT a cache-skip flag)
- [ ] 5.6 Tests: anubis at tier 1 → browser dispatched, jina/archive skipped; cap at 1; cache write happens

## 6. Gate

- [ ] 6.1 `make lint` clean
- [ ] 6.2 `make ty` clean
- [ ] 6.3 `make test` green, coverage ≥85%
- [ ] 6.4 CI: install `playwright install firefox` + `camoufox fetch` in lint/test workflow
- [ ] 6.5 Mark integration tests with `@pytest.mark.browser`; skip when binaries absent
- [ ] 6.6 Live demo: known Anubis-gated URL produces browser-tier success
- [ ] 6.7 Update `CLAUDE.md` (browser tier registered, gate `suggested_tier`, 1-browser cap, optional dep group)
- [ ] 6.8 Commit `PR7c: camoufox browser tier + gate signal`
- [ ] 6.9 Archive change via `openspec archive pr7c-browser-tier`
