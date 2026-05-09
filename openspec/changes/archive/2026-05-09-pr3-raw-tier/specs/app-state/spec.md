## MODIFIED Requirements

### Requirement: AppState is a dataclass holding shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)`. The dataclass SHALL hold a non-optional `settings: AppSettings` field plus typed placeholder fields for `sqlite`, `log_writer`, `proxy_pool`, `breakers`, `browser_pool`. In PR3, `sqlite` SHALL hold a live `aiosqlite.Connection` (not `None`) once `register_state` has run; `breakers` SHALL hold a populated registry of per-host purgatory circuit breakers. The remaining fields (`log_writer`, `proxy_pool`, `browser_pool`) SHALL still default to `None`.

#### Scenario: AppState carries a live sqlite connection after registration

- **WHEN** `register_state(app)` returns
- **THEN** `state.sqlite` is a non-None `aiosqlite.Connection` whose underlying database file is at `~/.a2web/cache.sqlite` (or `$A2WEB_CACHE_DIR/cache.sqlite` when set)

#### Scenario: AppState carries a breaker registry

- **WHEN** `register_state(app)` returns
- **THEN** `state.breakers` is a non-None object exposing `get(host: str) -> AsyncCircuitBreaker`

#### Scenario: Other resource fields remain None in PR3

- **WHEN** `register_state(app)` returns
- **THEN** `state.log_writer is None`, `state.proxy_pool is None`, `state.browser_pool is None` (filled in PR4 / PR7)

### Requirement: Per-App singleton registration

The system SHALL provide a `register_state(app, *, settings=None)` helper in `a2web.state` that registers a typed provider with the given `App` such that every dispatch on that App returns the same `AppState` instance. The helper SHALL open the sqlite connection (creating the schema if absent), build the breaker registry, and register an `atexit` hook that closes the sqlite connection cleanly on process exit.

#### Scenario: atexit hook closes sqlite

- **WHEN** the Python process terminates normally after `register_state` was called
- **THEN** the sqlite connection is closed (no open file descriptor; the WAL is checkpointed)

#### Scenario: Two Apps each get their own state and sqlite connection (canary)

- **WHEN** two independent `App` instances are constructed and `register_state` is called on each
- **THEN** the resolved `AppState` instances are not identity-equal AND `state1.sqlite is not state2.sqlite`
