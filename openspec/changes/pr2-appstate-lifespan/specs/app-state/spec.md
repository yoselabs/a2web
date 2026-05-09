## ADDED Requirements

### Requirement: AppState is a dataclass holding shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)`. The dataclass SHALL hold a non-optional `settings: AppSettings` field plus `Optional`-typed placeholder fields for `sqlite`, `log_writer`, `proxy_pool`, `breakers`, `browser_pool`. Placeholder fields default to `None`. Pydantic SHALL NOT be used for `AppState`.

#### Scenario: AppState is module-scope and slots-enabled

- **WHEN** `from a2web.state import AppState` is executed
- **THEN** `AppState` is importable, `AppState.__slots__` is non-empty, and `dataclasses.is_dataclass(AppState)` is `True`

#### Scenario: AppState carries settings

- **WHEN** `AppState(settings=AppSettings())` is constructed
- **THEN** `state.settings` is the provided `AppSettings` instance and all placeholder resource fields are `None`

#### Scenario: Unknown attributes are rejected

- **WHEN** code attempts `state.bogus = 1` on an `AppState` instance
- **THEN** Python raises `AttributeError` (slots enforcement)

### Requirement: Per-App singleton registration

The system SHALL provide a `register_state(app, *, settings=None)` helper in `a2web.state` that registers a typed provider with the given `App` such that every dispatch on that App returns the same `AppState` instance.

#### Scenario: Single App, repeated dispatches see one state

- **WHEN** `register_state(app)` is called once and the `fetch` tool is dispatched twice
- **THEN** both dispatches receive the same `AppState` object (identity equality)

#### Scenario: Two Apps each get their own state (canary)

- **WHEN** two independent `App` instances are constructed and `register_state` is called on each
- **THEN** dispatching `fetch` through each App yields two `AppState` instances that are not identity-equal and whose `settings` attributes are independent objects

#### Scenario: Custom settings injection

- **WHEN** `register_state(app, settings=custom_settings)` is called
- **THEN** the resolved `AppState.settings` is `custom_settings` (identity equality), bypassing the cached `get_settings()`

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
