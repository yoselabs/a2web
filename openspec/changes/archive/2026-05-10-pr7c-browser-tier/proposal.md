## Why

PR7a/PR7b closed two recovery channels (Jina for tier failures, archive for paywalls/block pages on 200-OK). The third escalation rung — **Camoufox browser** — is the canonical recovery path when JS *must* execute: Anubis PoW, Turnstile, Akamai BMP, Cloudflare managed challenge, JS-heavy SPAs whose initial HTML is a `<noscript>` shell. Today the gate detects these signals (`Verdict.anti_bot`, `block_page_detected` with anti-bot markers) but the orchestrator has nowhere to send them: jina mirrors the same blocked HTML, archive often lacks live snapshots for high-traffic dynamic sites. PR7c adds the browser tier and wires the gate's `suggested_tier` signal so the orchestrator can smart-skip intermediate tiers when JS is required.

This is also the last tier before the **proxy pool / circuit breakers** work (next PR per engineering.md §9). Building proxy infra before there are tiers to use it would be premature optimization; with browser tier landed, proxy routing has its full audience (raw + jina + browser, all per-host-tunable).

## What Changes

- **`tiers/browser.py`**: `BrowserTier` implementing `Tier` protocol with `name = "browser"`. Acquires a page from the `BrowserPool`, navigates, waits for network-idle (cap 30s), captures rendered HTML + final URL, releases page back to pool. Sync trafilatura inside the tier (parallels archive); populates `tier_extras["pre_rendered"]` so orchestrator skips re-extraction. Sets `tier_extras["from_browser"] = True`.
- **`browser/pool.py`**: `BrowserPool` (Camoufox via `playwright.async_api`). Lazy: no browser process at startup. `ensure_browser_pool(state)` opens the pool under an `asyncio.Lock` on first browser-tier invocation, caches on `state.browser_pool`. Persistent contexts keyed by host; page recycling 1:1 per fetch; idle eviction at 300s; resource budget 30s wall-clock per page. `atexit` hook closes the pool on a fresh loop (mirrors PR7a's lazy sqlite pattern — a2kit v0.23 has no lifespan hook to forward).
- **`gate/block_detector.py`**: extend `GateResult` with `suggested_tier: str | None`. Populate from a hardcoded signal→tier table per engineering.md §2:
  - `anubis` marker → `browser`
  - `cf-mitigated: challenge` header (when wired) → `browser`
  - `cf-chl-bypass` cookie / "Just a moment" interstitial → `tls_impersonate` (no-op for v0.1 — raw already uses curl_cffi)
  - turnstile widget marker → `browser`
  - akamai BMP sensor markers → `browser`
  - `<noscript>Please enable JavaScript</noscript>` + body < 500 chars + script-heavy → `browser` (`js_required`)
- **`fetcher.py`**: when gate returns `suggested_tier == "browser"`, dispatch the browser tier as the next step regardless of `TIER_ORDER` position (matches archive's out-of-band dispatch). Cap = 1 browser dispatch per fetch (anti-loop). When `suggested_tier == "tls_impersonate"` and the producing tier was already raw, no-op (raw already uses curl_cffi).
- **`settings.py`**: new keys `browser_enabled: bool = True`, `browser_max_pool: int = 4`, `browser_idle_timeout_s: int = 300`, `browser_page_budget_s: int = 30`. All env-overridable via `A2WEB_BROWSER_*`.
- **`state.py`**: `AppState.browser_pool: Optional[BrowserPool]` placeholder already present; add `ensure_browser_pool(state)` async helper and `_close_browser_pool` atexit hook.
- **`pyproject.toml`**: add `camoufox[geoip]` and `playwright` (extras gated under `browser` optional dep group; CI installs them; runtime degrades gracefully if absent — `BrowserTier.fetch` returns a `connection_error` verdict with `operator_hints[code=browser_unavailable]` if Camoufox import fails).
- **`TIER_ORDER` unchanged** — browser is opt-in via gate signal, never default. Adding it to the cascade would burn 2–4s cold-start on the 80%+ of URLs that don't need JS.
- **Caching**: archive-style — `tier_extras["from_browser"]=True` results still cache (unlike archive). Browser-rendered content is the live page; safe to cache under the standard URL+profile_hash key.

## Capabilities

### New Capabilities

- `browser-tier`: Camoufox-based JS-execution tier, lazy-launched, pool-managed, dispatched out-of-band by gate signal

### Modified Capabilities

- `quality-gate`: gate result carries optional `suggested_tier` to drive smart-escalation
- `tier-pipeline`: orchestrator dispatches browser tier when gate suggests it; smart-skip intermediate tiers (e.g., anubis at tier 1 → jump straight to browser, skip jina/archive that would also fail)

## Impact

- `pyproject.toml`: new optional deps `camoufox[geoip]`, `playwright` under `[project.optional-dependencies] browser`
- `src/a2web/browser/__init__.py` + `pool.py`: new package, ~200 LOC
- `src/a2web/tiers/browser.py`: new file, ~100 LOC
- `src/a2web/gate/block_detector.py`: `suggested_tier` field + signal table, ~30 LOC delta
- `src/a2web/state.py`: `ensure_browser_pool` + atexit hook, ~40 LOC delta
- `src/a2web/fetcher.py`: gate-driven browser dispatch + 1-browser cap, ~30 LOC delta
- `src/a2web/settings.py`: 4 new fields
- `src/a2web/tiers/__init__.py`: register `BrowserTier` in `REGISTRY` (NOT in `TIER_ORDER`)
- Tests: gate signal table per row; `BrowserPool` lazy init + atexit; `BrowserTier` happy path against a local fixture (Anubis-marked HTML served from a test server); orchestrator dispatch on gate signal; 1-browser cap; Camoufox-import-fails graceful degradation
- CI: install `playwright install firefox` + `camoufox fetch` in gate workflow; mark browser-tier integration tests with `@pytest.mark.browser` so they're skipped when binaries absent
