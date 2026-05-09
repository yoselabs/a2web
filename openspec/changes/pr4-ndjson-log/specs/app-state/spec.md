## MODIFIED Requirements

### Requirement: AppState is a dataclass holding shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)`. The dataclass SHALL hold a non-optional `settings: AppSettings` field plus typed placeholder fields for `sqlite`, `log_writer`, `proxy_pool`, `breakers`, `browser_pool`. After PR4, `breakers` SHALL hold a populated `AsyncCircuitBreakerFactory` and `log_writer` SHALL hold a `LogWriter` instance (or a no-op writer when `settings.log_enabled is False`). `sqlite` continues to default to `None` and is opened per-fetch by the orchestrator. `proxy_pool` and `browser_pool` continue to default to `None` (filled in PR7).

#### Scenario: log_writer is populated after register_state

- **WHEN** `register_state(app)` is called with default settings
- **THEN** `state.log_writer` is a `LogWriter` instance whose `write_record` coroutine is callable

#### Scenario: log_writer is no-op when disabled

- **WHEN** `register_state(app, settings=AppSettings(log_enabled=False))` is called
- **THEN** `state.log_writer.write_record(record)` returns successfully without touching the filesystem

#### Scenario: Other resource fields remain None in PR4

- **WHEN** `register_state(app)` returns
- **THEN** `state.sqlite is None`, `state.proxy_pool is None`, `state.browser_pool is None` (filled in later PRs)
