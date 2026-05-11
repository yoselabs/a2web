## REMOVED Requirements

### Requirement: Browser pool is lazy and atexit-cleaned

**Reason:** Lifecycle replaced by `@app.on_shutdown` hook (a2kit v0.24+). The `atexit` hook and `_atexit_close` function are deleted; `ensure_browser_pool(state)` lazy-lock pattern stays at the *tier* level (because Camoufox is an optional dep and we should not start it at App startup), but the close side moves to the shutdown hook.

**Migration:** Keep lazy-open inside `BrowserTier.fetch` (so missing camoufox stays a connection_error, not a startup crash). Replace the `atexit` close path with:

```python
@app.on_shutdown
async def _close_browser(state: AppState) -> None:
    if state.browser_pool is not None:
        await state.browser_pool.close()
```

Test fixtures use `a2kit.testing.client(app)` which fires startup/shutdown hooks automatically; the manual `teardown_state_for_test` helper is deleted.

## MODIFIED Requirements

### Requirement: Browser tier executes JS via Camoufox pool

The system SHALL define `BrowserTier` in `src/a2web/tiers/browser.py` implementing the `Tier` protocol with `name = "browser"`. Behavior preserved from v0.1.0 at the call-site level. The tier SHALL populate the *typed* `TierResult.pre_rendered: Rendered | None` field (not `tier_extras["pre_rendered"]: dict`) and set the typed `from_browser: bool`, `js_executed: bool`, `browser_wall_ms: int | None`, `browser_bytes: int | None` fields.

The tier SHALL emit `TierHeartbeat` events at 2-second intervals during page-load wait, carrying the current target URL in `detail`. Heartbeats SHALL cease when the page completes or times out.

#### Scenario: Typed pre_rendered field populated on success

- **WHEN** the browser tier completes successfully against a JS-gated page
- **THEN** `tier_result.pre_rendered` is a `Rendered` instance with populated `content_md`, `title`, etc., AND `tier_result.from_browser is True` AND `tier_result.js_executed is True`

#### Scenario: Heartbeat emitted during slow page

- **WHEN** the tier dispatches a page that takes 6 seconds to load
- **THEN** at least two `TierHeartbeat` events with `step="browser"` are emitted before the final `TierEnded` event

#### Scenario: Heartbeats stop on page complete

- **WHEN** the tier returns (any verdict)
- **THEN** no further `TierHeartbeat` events are emitted for this tier invocation

### Requirement: Browser tier degrades gracefully without Camoufox

Behavior preserved from v0.1.0: missing Camoufox import yields `verdict == Verdict.connection_error` with a populated `operator_hint` (typed field, not dict). The tier SHALL set the typed `tier_result.operator_hint: OperatorHint | None` rather than `tier_extras["operator_hint"]: dict`.

#### Scenario: Camoufox not installed

- **WHEN** the `[browser]` extras are not installed and the gate dispatches the browser tier
- **THEN** the result is `verdict == Verdict.connection_error` AND `tier_result.operator_hint.code == "browser_unavailable"` AND the orchestrator records the dispatch as failed without crashing

### Requirement: Browser tier is in REGISTRY but not in TIER_ORDER

The system SHALL register `BrowserTier` in `REGISTRY` under key `"browser"` but SHALL NOT include `"browser"` in `TIER_ORDER`. Default fetches MUST NOT invoke the browser tier; it SHALL be dispatched out-of-band by the orchestrator only when the gate sets `suggested_tier == SuggestedTier.browser`. This is the **escalation-dispatch contract** — tiers in REGISTRY but not in TIER_ORDER are dispatched via the playbook (`browser` on `gate.suggested_tier == browser`, `archive` on `RetryViaArchive` action). The footnote comments in `tiers/__init__.py`, `tiers/archive.py`, and `tiers/browser.py` referencing this rule SHALL be removed; a single docstring at `tiers/__init__.py` SHALL be the canonical statement.

#### Scenario: TIER_ORDER excludes browser

- **WHEN** the registry is imported
- **THEN** `"browser" in REGISTRY` and `"browser" not in TIER_ORDER`

## ADDED Requirements

### Requirement: BrowserPool moves to workspace package

The `BrowserPool` class SHALL move from `src/a2web/browser/pool.py` to `packages/browser-pool/src/browser_pool/pool.py`. The package SHALL declare its own deps (`playwright`, `camoufox` as optional extras), define its own narrow types, and not import any symbol from a2web. `src/a2web/browser/__init__.py` SHALL become a thin adapter — `BrowserTier` keeps living in a2web's tier tree, but the pool lifecycle (`start`, `acquire_page`, `release_page`, `close`) is package-owned.

#### Scenario: Package isolation

- **WHEN** lint runs over `packages/browser-pool/src/`
- **THEN** zero `from a2web` or `import a2web` matches are found

#### Scenario: BrowserTier uses package-owned pool

- **WHEN** `BrowserTier.fetch` runs
- **THEN** it acquires the page from a `browser_pool.BrowserPool` instance (held on `state.browser_pool`); a2web's adapter translates package result types to a2web `TierResult` typed fields
