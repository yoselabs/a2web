# browser-tier — scroll-on-thin + stderr capture

## ADDED Requirements

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

### Requirement: Subprocess stderr from camoufox/playwright lands in LDD diagnostics

The browser tier SHALL capture stderr from camoufox's underlying playwright Node.js subprocess and route any non-empty lines to LDD as `StageStarted("browser_subprocess_stderr")` / `StageEnded(...)` events with the captured text in `extra={"stderr": <trimmed-line>}`. The tier SHALL NOT inherit stderr from the Python parent process. When camoufox/playwright internals raise (e.g., the `TypeError: Cannot read properties of undefined` seen on TechCrunch), no JS stack trace SHALL appear on the user's terminal; instead a single LDD event records the error and the tier returns `verdict == Verdict.connection_error` (already-existing path).

#### Scenario: Playwright internal error is captured, not leaked

- **WHEN** camoufox encounters an internal playwright error during `page.goto` (e.g., the TechCrunch coreBundle.js TypeError)
- **THEN** the JS stack trace is captured into one or more `browser_subprocess_stderr` LDD events; the user's terminal sees no Node.js output; the tier returns `verdict == Verdict.connection_error`

#### Scenario: Clean browser fetch emits no stderr events

- **WHEN** the browser tier successfully renders a page with no subprocess errors
- **THEN** no `browser_subprocess_stderr` events are emitted (zero LDD noise on the happy path)
