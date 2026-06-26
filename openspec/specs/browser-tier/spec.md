# browser-tier Specification

## Purpose
TBD - created by archiving change pr7c-browser-tier. Update Purpose after archive.
## Requirements
### Requirement: Browser tier executes JS via Camoufox pool

The system SHALL define `BrowserTier` in `src/a2web/tiers/browser.py` implementing the `Tier` protocol with `name = "browser"`. `BrowserTier.fetch` SHALL delegate rendering to the **selected `BrowserBackend`** (`backend.render(url, cookies=..., budget_s=..., js_heavy=...)`) rather than driving a Playwright `Page` directly. The tier SHALL own only the engine-agnostic tail: run trafilatura over the returned `RenderedPage.html`, populate `pre_rendered` (typed `Rendered`: `content_md`, `title`, `byline`, `headings`), set `from_browser = True` and `js_executed = RenderedPage.js_executed`, run the quality gate, and assemble the `TierResult`. The `TierResult` shape and every field it carries SHALL be unchanged from the pre-refactor tier (the response envelope is frozen).

The Playwright-specific mechanics the tier previously performed inline — per-host context pool, cookie seeding, navigation + network-idle budget, scroll-on-thin re-capture, driver-stderr capture, and the `browser_internal_error` hint — are realized by `PlaywrightBackend` behind the `BrowserBackend` interface (see the `browser-backend` capability). The tier no longer references `BrowserPool` or any Playwright type.

#### Scenario: Anubis-gated page renders post-PoW

- **WHEN** the URL serves an Anubis interstitial that resolves to real content after JS PoW
- **THEN** the selected backend's `render` returns the post-PoW HTML and the tier returns `verdict == Verdict.ok` with the content in `pre_rendered.content_md`

#### Scenario: Network-idle wait exceeds page budget

- **WHEN** rendering does not reach network-idle within `budget_s`
- **THEN** the backend returns a timed-out result and the tier returns `verdict == Verdict.timeout` with `browser_wall_ms >= budget_s * 1000`

#### Scenario: Tier holds no Playwright reference

- **WHEN** `tiers/browser.py` is imported
- **THEN** it imports no Playwright/Camoufox symbol and references no `BrowserPool` — it depends only on the `BrowserBackend` interface and `RenderedPage`

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

### Requirement: Browser tier scrolls and retries when first snapshot is thin

After the initial `page.goto(url, wait_until="networkidle")` completes, the browser tier SHALL check the rendered HTML length. If `len(html) < 4096` chars AND the host is in the `JS_HEAVY_HOSTS` set (the same set used by the quality gate), the tier SHALL:

1. Evaluate `window.scrollTo(0, document.body.scrollHeight)` in the page context.
2. `wait_for_load_state("networkidle")` with a 2,000 ms cap.
3. Re-capture the rendered HTML and final URL.
4. Use whichever capture (initial or post-scroll) has the larger body length.

The tier SHALL emit `StageStarted("browser_scroll_retry")` and `StageEnded("browser_scroll_retry")` LDD events around the retry so operators can measure how often it fires. If the scroll retry itself times out or raises, the tier SHALL fall back to the original capture (no failure introduced by the retry path).

#### Scenario: Trendyol lazy-loaded grid is recovered

- **WHEN** the browser tier first-snapshot for `https://www.trendyol.com/sr?q=sirt+cantasi` returns ~640 chars (nav-menu only) and `trendyol.com` is in `JS_HEAVY_HOSTS`
- **THEN** the tier executes the scroll-to-bottom JS, waits for networkidle, and re-captures; the final result contains substantially more content (the product grid)

#### Scenario: Non-JS-heavy host does not pay the scroll cost

- **WHEN** the browser tier first-snapshot returns ~600 chars from a host NOT in `JS_HEAVY_HOSTS`
- **THEN** no scroll retry runs; the original capture is returned as-is

#### Scenario: Scroll retry timeout falls back to first capture

- **WHEN** the scroll retry's `wait_for_load_state("networkidle")` exceeds 2,000 ms
- **THEN** the tier emits `StageEnded("browser_scroll_retry", verdict="timeout")` and returns the original (thin) capture; no exception propagates

### Requirement: Browser driver subprocess stderr is captured, not leaked

The browser tier SHALL capture stderr emitted by Camoufox's underlying Playwright Node.js driver process so that no driver/JS stack trace reaches the operator's terminal. The tier SHALL NOT let the driver subprocess inherit the Python parent's stderr (fd 2) uncaptured. Each non-empty captured line SHALL be routed through the current logging substrate via `await a2kit.log.info(...)` as a typed event (defined in `src/a2web/events/types.py`), carrying the trimmed line in its fields. When the driver emits an internal error (e.g. the `FFPage._onUncaughtError` TypeError seen on JS-heavy SPAs), the captured trace SHALL appear only in the logging substrate and the operator's terminal SHALL see no raw Node.js output. A clean render SHALL emit zero such events.

#### Scenario: Driver internal error is captured, not leaked to the terminal

- **WHEN** the Playwright Firefox driver writes an internal stack trace to its stderr during a browser fetch (e.g. the `coreBundle.js` `pageError.location.url` TypeError)
- **THEN** the trace is captured and emitted as one or more typed log events via `a2kit.log.info`, and no raw Node.js stack trace appears on the operator's terminal

#### Scenario: Clean browser fetch emits no stderr events

- **WHEN** the browser tier successfully renders a page and the driver writes nothing to stderr
- **THEN** zero subprocess-stderr log events are emitted (no noise on the happy path)

### Requirement: Browser tier surfaces internal driver errors as an OperatorHint

When `BrowserTier.fetch` catches an internal exception on the navigation path (network reset, driver error, or other non-timeout failure during `page.goto` / content capture), the tier SHALL NOT discard the exception. It SHALL attach an `OperatorHint` to the returned `TierResult.operator_hint` with a stable `code == "browser_internal_error"`, a `message` that is a single-line summary of the exception type and text (never a multi-line stack dump), and a non-null actionable `fix`. The verdict SHALL remain `Verdict.connection_error` (the existing path). The orchestrator's existing tier-hint surfacing SHALL carry the hint onto the response `operator_hints`.

#### Scenario: Navigation exception produces a structured hint instead of silent loss

- **WHEN** `page.goto` raises a non-timeout exception inside `BrowserTier.fetch`
- **THEN** the result has `verdict == Verdict.connection_error` and a populated `operator_hint` with `code == "browser_internal_error"`, a one-line `message`, and a non-null `fix`

#### Scenario: Internal-error hint reaches the response

- **WHEN** the orchestrator dispatches the browser tier and the tier returns a `browser_internal_error` hint
- **THEN** that hint appears in the response `operator_hints` list

#### Scenario: Hint message carries no multi-line stack dump

- **WHEN** the caught exception's string representation spans multiple lines
- **THEN** the `OperatorHint.message` is a single trimmed line (the multi-line detail belongs in the captured-stderr log events, not the wire hint)

### Requirement: Browser tier has an opt-in real-browser smoke check

The test suite SHALL include a real-browser smoke check that launches the actual Camoufox binary (opting out of the autouse `_UnavailableBrowserTier` stub), navigates a deterministic local JavaScript-rendering fixture, and asserts the tier returns non-empty rendered markdown with `js_executed == True`. The check SHALL be gated behind a registered pytest marker (`browser`) and SHALL be excluded from the default `make check` / `make test` run (`-m "not browser"`). It SHALL auto-skip when the Camoufox binary is unavailable. A dedicated `make` target SHALL run it on demand.

#### Scenario: Smoke check is excluded from the default gate

- **WHEN** `make check` runs
- **THEN** the real-browser smoke check is deselected (the marker is excluded) and no Camoufox process launches during the default gate

#### Scenario: Smoke check verifies real JS execution on demand

- **WHEN** the `browser`-marked smoke check runs against the local JS-rendering fixture with Camoufox installed
- **THEN** it launches a real browser, executes the fixture's JavaScript, and asserts `verdict == Verdict.ok` with non-empty `pre_rendered.content_md` and `js_executed == True`

#### Scenario: Smoke check skips when Camoufox is absent

- **WHEN** the `browser`-marked smoke check runs in an environment without the Camoufox binary
- **THEN** the check is skipped (not failed)

