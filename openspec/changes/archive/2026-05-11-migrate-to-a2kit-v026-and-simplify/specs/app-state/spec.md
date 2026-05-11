## MODIFIED Requirements

### Requirement: AppState is a dataclass holding shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)`. The dataclass SHALL hold:

- `settings: AppSettings` — non-optional, immutable for the App's lifetime.
- `sqlite: aiosqlite.Connection` — non-optional, opened by the `@app.on_startup` hook before the first dispatch.
- `breakers: AsyncCircuitBreakerFactory` — non-optional, constructed in the factory.
- `log_writer: LogWriter` — non-optional; a no-op writer when `settings.log_enabled is False`.
- `proxy_pool: ProxyPool` — non-optional, constructed in the factory (in-memory health state is per-App).
- `browser_pool: BrowserPool | None` — optional, lazily opened on first browser-tier dispatch (Camoufox is an optional dep).

The dataclass SHALL NOT carry `sqlite_lock`, `browser_lock`, or `proxy_lock` fields — lazy-locking is replaced by lifecycle hooks. The `extras: dict[str, Any]` field SHALL be removed (no consumer remains post-migration).

#### Scenario: sqlite is non-optional after startup

- **WHEN** the `@app.on_startup` hook completes
- **THEN** `state.sqlite` is an open `aiosqlite.Connection` and dispatching a tool sees a non-None handle

#### Scenario: browser_pool stays lazy

- **WHEN** the App starts and no fetch triggers the browser tier
- **THEN** `state.browser_pool is None` and no Camoufox process is launched

#### Scenario: log_writer is no-op when disabled

- **WHEN** an App is built with `AppSettings(log_enabled=False)`
- **THEN** `state.log_writer.write_record(record)` returns successfully without touching the filesystem

## REMOVED Requirements

### Requirement: Per-App singleton registration

**Reason:** Replaced by `app.singleton(AppState, factory=build_state)` (a2kit v0.24+) + `@app.on_startup` / `@app.on_shutdown` hooks (a2kit v0.24+). The `register_state` closure, the `atexit` hook, and the lazy `ensure_*` lock pattern all disappear.

**Migration:** Compose the App imperatively in `src/a2web/server.py`:

```python
app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())
app.singleton(AppState, factory=build_state)

@app.on_startup
async def _open(state: AppState) -> None:
    state.sqlite = await open_sqlite_with_schema(state.settings)

@app.on_shutdown
async def _close(state: AppState) -> None:
    if state.sqlite is not None:
        await state.sqlite.close()
    if state.browser_pool is not None:
        await state.browser_pool.close()
```

Tests that previously called `bootstrap_state_for_test` / `teardown_state_for_test` SHALL switch to `a2kit.testing.client(app)` for end-to-end coverage or construct an `AppState` directly for narrow unit tests.

## ADDED Requirements

### Requirement: build_state factory function

The system SHALL provide `build_state(settings: AppSettings | None = None) -> AppState` in `src/a2web/state.py`. The function SHALL return a fully-populated `AppState` with all non-optional fields set. The `sqlite` field SHALL be assigned in the `@app.on_startup` hook, not the factory (the connection requires an event loop).

#### Scenario: Factory returns a complete state minus sqlite

- **WHEN** `build_state()` is called
- **THEN** the returned `AppState` has `settings`, `breakers`, `log_writer`, `proxy_pool` populated; `sqlite` is `None` (filled by the startup hook); `browser_pool` is `None` (stays lazy)

#### Scenario: Custom settings flow through

- **WHEN** `build_state(settings=AppSettings(stealth=True))` is called
- **THEN** `state.settings.stealth is True` and downstream tiers see the override
