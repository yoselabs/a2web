# app-state Specification

## Purpose
TBD - created by archiving change pr2-appstate-lifespan. Update Purpose after archive.
## Requirements
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

### Requirement: Per-App singleton registration

The system SHALL provide a `register_state(app, *, settings=None)` helper in `a2web.state` that registers a typed provider with the given `App` such that every dispatch on that App returns the same `AppState` instance. The helper SHALL open the sqlite connection (creating the schema if absent), build the breaker registry, and register an `atexit` hook that closes the sqlite connection cleanly on process exit.

#### Scenario: atexit hook closes sqlite

- **WHEN** the Python process terminates normally after `register_state` was called
- **THEN** the sqlite connection is closed (no open file descriptor; the WAL is checkpointed)

#### Scenario: Two Apps each get their own state and sqlite connection (canary)

- **WHEN** two independent `App` instances are constructed and `register_state` is called on each
- **THEN** the resolved `AppState` instances are not identity-equal AND `state1.sqlite is not state2.sqlite`

### Requirement: fetch tool resolves AppState via DI

The system SHALL update `WebRouter.fetch` to declare `state: AppState` as a kwarg. The tool SHALL still return a `FetchResponse` with `tier="stub"` and SHALL incorporate `state.settings.diagnostics_default` into the response narrative to confirm resolution.

#### Scenario: Tool receives the registered AppState

- **WHEN** the `fetch` tool is invoked through the App pipeline
- **THEN** the `state` kwarg is bound to the App's registered `AppState` instance and the response narrative includes the value of `state.settings.diagnostics_default`

#### Scenario: MCP schema still lists `fetch` as one tool

- **WHEN** an MCP client lists tools
- **THEN** `fetch` appears exactly once with the same name and the `state` kwarg is excluded from the wire schema (DI parameter, not a user input)

### Requirement: Server composition registers AppState

The system SHALL update `src/a2web/server.py` so the App composition includes `register_state(app)` (or equivalent) after `add_router(WebRouter())`. The change SHALL NOT introduce `connections_cli` or any FastMCP lifespan in PR2.

#### Scenario: Server module registers state on import

- **WHEN** `from a2web.server import app` is executed
- **THEN** `app.has_provider(AppState)` returns `True`

#### Scenario: No connections CLI surface

- **WHEN** the user runs `a2web --help`
- **THEN** the output does NOT include a `connections` subcommand group (PR1's option B preserved)

