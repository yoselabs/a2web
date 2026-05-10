## ADDED Requirements

### Requirement: Browser tier executes JS via Camoufox pool

The system SHALL define `BrowserTier` in `src/a2web/tiers/browser.py` implementing the `Tier` protocol with `name = "browser"`. `BrowserTier.fetch` SHALL acquire a page from the lazily-initialized `BrowserPool` (Camoufox via `playwright.async_api`), navigate to the target URL, wait for network-idle (cap = `settings.browser_page_budget_s` seconds), capture the rendered HTML and final URL after redirects, and release the page back to the pool.

The tier SHALL run trafilatura on the rendered HTML and populate `tier_extras["pre_rendered"] = {content_md, title, byline, headings}` so the orchestrator skips re-extraction. The tier SHALL set `tier_extras["from_browser"] = True` and `tier_extras["js_executed"] = True` on every successful result.

#### Scenario: Anubis-gated page renders post-PoW

- **WHEN** the URL serves an Anubis interstitial that resolves to real content after JS PoW
- **THEN** the tier returns `verdict == Verdict.ok` with the post-PoW content in `tier_extras["pre_rendered"].content_md`

#### Scenario: Network-idle wait exceeds page budget

- **WHEN** the page does not reach network-idle within `settings.browser_page_budget_s`
- **THEN** the page is closed and the tier returns `verdict == Verdict.timeout` with `tier_extras["browser_wall_ms"] >= browser_page_budget_s * 1000`

### Requirement: Browser pool is lazy and atexit-cleaned

The system SHALL NOT launch any Camoufox process at startup. `state.browser_pool` SHALL remain `None` until the first browser-tier dispatch calls `ensure_browser_pool(state)`, which SHALL open the pool under an `asyncio.Lock` and cache it on `state.browser_pool`. A process-level `atexit` hook SHALL close the pool on a fresh event loop. Test fixtures SHALL close the pool explicitly via `teardown_state_for_test` to prevent the atexit hook from firing on a closed test loop.

#### Scenario: No Camoufox process when browser tier never dispatched

- **WHEN** a fetch completes via raw or jina with no gate signal
- **THEN** no Camoufox process exists and `state.browser_pool is None`

#### Scenario: First browser dispatch initializes pool exactly once

- **WHEN** two concurrent fetches both trigger browser dispatch
- **THEN** `ensure_browser_pool` initializes the pool exactly once (lock-guarded) and both fetches receive pages from it

### Requirement: Browser pool persists per-host contexts with LRU eviction

The pool SHALL keep at most `settings.browser_max_pool` contexts (default 4), keyed by host. Contexts SHALL be reused across same-host fetches to preserve cookies. When a new host arrives at cap, the least-recently-used context SHALL be closed and evicted. Idle contexts SHALL be evicted after `settings.browser_idle_timeout_s` seconds.

#### Scenario: Same-host fetches reuse context

- **WHEN** two consecutive fetches target `https://example.com/a` and `https://example.com/b`
- **THEN** both pages are created from the same `BrowserContext` (cookie jar shared)

#### Scenario: New host at cap evicts LRU

- **WHEN** `max_pool == 4` and 4 distinct hosts have warm contexts, then a 5th host arrives
- **THEN** the least-recently-used context is closed and the 5th host gets a fresh context

### Requirement: Browser tier degrades gracefully without Camoufox

When `from camoufox.async_api import AsyncCamoufox` raises `ImportError`, the tier SHALL return `verdict == Verdict.connection_error` with `operator_hints` containing a hint with `code == "browser_unavailable"` and a `fix` field describing the install command. The orchestrator SHALL NOT crash.

#### Scenario: Camoufox not installed

- **WHEN** the `[browser]` extras are not installed and the gate dispatches the browser tier
- **THEN** the result is `verdict == Verdict.connection_error` with `operator_hints[code=browser_unavailable]` and the orchestrator records the dispatch as failed without crashing

### Requirement: Browser tier is in REGISTRY but not in TIER_ORDER

The system SHALL register `BrowserTier` in `REGISTRY` under key `"browser"` but SHALL NOT include `"browser"` in `TIER_ORDER`. Default fetches SHALL never invoke the browser tier; it is dispatched out-of-band by the orchestrator only when the gate sets `suggested_tier == "browser"`.

#### Scenario: TIER_ORDER excludes browser

- **WHEN** the registry is imported
- **THEN** `"browser" in REGISTRY` and `"browser" not in TIER_ORDER`
