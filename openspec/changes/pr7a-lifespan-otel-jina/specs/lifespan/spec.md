## ADDED Requirements

### Requirement: Lazy sqlite singleton

The system SHALL provide `ensure_sqlite(state: AppState) -> aiosqlite.Connection` in `src/a2web/state.py`. The first call SHALL open a fresh `aiosqlite` connection (running `open_sqlite_with_schema`), assign it to `state.sqlite`, and return it. Subsequent calls within the same process SHALL return the cached connection. Concurrent first-callers SHALL be serialized by an `asyncio.Lock` stored on `AppState` so only one open occurs.

#### Scenario: sqlite is opened once per process

- **WHEN** N consecutive `fetch` invocations run on the same `AppState`
- **THEN** `state.sqlite` is the same connection object across all N invocations and `aiosqlite.connect` is called exactly once

#### Scenario: Concurrent first-callers serialize

- **WHEN** two coroutines call `ensure_sqlite(state)` before either has completed
- **THEN** exactly one `aiosqlite.connect` happens and both coroutines receive the same connection

### Requirement: atexit cleanup hook

The system SHALL register an `atexit` handler at `register_state` time that, if `state.sqlite is not None` at process exit, runs the close coroutine on a fresh event loop. Errors during atexit cleanup SHALL be swallowed (best-effort; the WAL is durable on disk).

#### Scenario: Process exit closes sqlite

- **WHEN** the Python process terminates normally after at least one fetch
- **THEN** the sqlite connection is closed (no open file descriptor; WAL is checkpointed)

### Requirement: Test bootstrap helper

The system SHALL provide async `bootstrap_state_for_test(settings: AppSettings | None = None) -> AppState` and `teardown_state_for_test(state: AppState) -> None` in `src/a2web/state.py`. `bootstrap_state_for_test` SHALL open sqlite via `ensure_sqlite` and return a fully populated `AppState`. Tests MUST call `teardown_state_for_test` to close the sqlite connection.

#### Scenario: Helper returns a usable AppState

- **WHEN** `bootstrap_state_for_test()` is awaited inside an async test
- **THEN** `state.sqlite is not None`, `state.breakers is not None`, `state.log_writer is not None`

### Requirement: Orchestrator uses ensure_sqlite

The orchestrator's `fetch(url, *, state, bus=None)` SHALL obtain its sqlite connection via `await ensure_sqlite(state)` and SHALL NOT open or close a per-fetch connection. Cache reads/writes SHALL operate against `state.sqlite`.

#### Scenario: Per-fetch sqlite open is gone

- **WHEN** `fetch(url, *, state, bus=None)` runs
- **THEN** the orchestrator does not call `aiosqlite.connect` directly; the connection is read from `state.sqlite` (populated by `ensure_sqlite`)
