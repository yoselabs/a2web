# browser-tier Specification

## Purpose
TBD - created by archiving change pr7c-browser-tier. Update Purpose after archive.
## Requirements
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

### Requirement: Browser tier seeds context with per-fetch cookies

`BrowserTier.fetch` SHALL accept an optional `cookies_full: list[Cookie] | None = None` keyword carrying full Cookie objects (name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite). When set and non-empty, the tier SHALL call `context.add_cookies([...])` on the per-host `BrowserContext` BEFORE navigation, converting each `Cookie` to Playwright's shape:

- `name` → `name`
- `value` → `value`
- `host_key` → `domain`
- `path` → `path`
- `expires_utc` (unix seconds, None → -1 for session) → `expires`
- `is_secure` (0/1) → `secure` (bool)
- `is_httponly` (0/1) → `httpOnly` (bool)
- `samesite` (`"lax"|"strict"|"none"|None`) → `sameSite` (`"Lax"|"Strict"|"None"`); None omitted

When unset or empty, no `add_cookies` call SHALL be made (current behavior unchanged).

The seeded cookies SHALL augment any cookies already in the warm context — `add_cookies` overwrites by `(name, domain, path)` triple, which is the desired semantic when a refreshed mirror provides a newer value for an existing cookie.

#### Scenario: No add_cookies call when cookies_full is None

- **WHEN** `BrowserTier.fetch(url, cookies_full=None)` runs
- **THEN** the captured `BrowserContext.add_cookies` is not called

#### Scenario: Cookies are seeded with correct Playwright shape

- **WHEN** `BrowserTier.fetch` runs with one cookie `(name="sid", value="x", host_key=".example.com", path="/", expires_utc=None, is_secure=1, is_httponly=1, samesite="lax")`
- **THEN** `add_cookies` is called once with a list whose single element has `name="sid"`, `value="x"`, `domain=".example.com"`, `path="/"`, `expires=-1`, `secure=True`, `httpOnly=True`, `sameSite="Lax"`

#### Scenario: SameSite None omitted from Playwright payload

- **WHEN** the source cookie has `samesite=None`
- **THEN** the resulting Playwright cookie dict has no `sameSite` key

#### Scenario: add_cookies runs before navigation

- **WHEN** `BrowserTier.fetch` is invoked with non-empty cookies
- **THEN** the captured call order is `add_cookies(...)` then `page.goto(url)`; never the reverse

### Requirement: Browser tier does not log cookie values

The browser tier SHALL NOT include cookie values in any LDD event payload, structlog record, or diagnostic row. Counts and host_keys are permitted; values are not.

#### Scenario: LDD event carries no values

- **WHEN** the browser tier emits an LDD event for a fetch with 3 cookies attached
- **THEN** the captured event payload contains no value substring of any of the 3 cookies

