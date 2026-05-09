## MODIFIED Requirements

### Requirement: AppState is a dataclass holding shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)`. The dataclass SHALL hold a non-optional `settings: AppSettings` field plus typed placeholder fields for `sqlite`, `log_writer`, `proxy_pool`, `breakers`, `browser_pool`. After PR7a, `breakers` and `log_writer` SHALL be populated by `register_state`. `sqlite` SHALL be lazily opened on first use via `ensure_sqlite(state)` and cached on the dataclass; an `asyncio.Lock` on `AppState` serializes concurrent first-callers. `proxy_pool` and `browser_pool` continue to default to `None` (filled in PR7b/c).

#### Scenario: log_writer is populated after register_state

- **WHEN** `register_state(app)` is called with default settings
- **THEN** `state.log_writer` is a `LogWriter` instance whose `write_record` coroutine is callable

#### Scenario: log_writer is no-op when disabled

- **WHEN** `register_state(app, settings=AppSettings(log_enabled=False))` is called
- **THEN** `state.log_writer.write_record(record)` returns successfully without touching the filesystem

#### Scenario: sqlite is None until first ensure_sqlite

- **WHEN** `register_state(app)` returns and no fetch has run
- **THEN** `state.sqlite is None`

#### Scenario: sqlite is populated after first ensure_sqlite

- **WHEN** `await ensure_sqlite(state)` runs
- **THEN** `state.sqlite is not None` and queries against it succeed (schema is present)

#### Scenario: proxy_pool and browser_pool remain None in PR7a

- **WHEN** `register_state(app)` returns
- **THEN** `state.proxy_pool is None` and `state.browser_pool is None`

### Requirement: Per-App singleton registration

The system SHALL provide a `register_state(app, *, settings=None)` helper in `a2web.state` that registers a typed provider with the given `App` such that every dispatch on that App returns the same `AppState` instance. After PR7a, the helper SHALL build `breakers`, `log_writer`, and the `asyncio.Lock` synchronously, register an `atexit` cleanup hook for sqlite, and bind the provider. `sqlite` is left None and opened lazily by `ensure_sqlite`.

#### Scenario: Two Apps each get their own state and sqlite connection (canary)

- **WHEN** two independent `App` instances are constructed and each runs at least one fetch
- **THEN** the resolved `AppState` instances are not identity-equal AND `state1.sqlite is not state2.sqlite`

#### Scenario: register_state alone does not open sqlite

- **WHEN** `register_state(app)` is called and no fetch has run
- **THEN** `state.sqlite is None`
