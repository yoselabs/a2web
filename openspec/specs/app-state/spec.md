# app-state Specification

## Purpose
The always-on shared state of the fetch pipeline: `AppState`, a slotted dataclass
holding the resources every fetch needs (`settings`, `breakers`, `proxy_pool`,
`sqlite`), constructed through the one composition root. Heavy/conditional
resources live as `Lazy[T]` thunks on `Components`, not here.
## Requirements
### Requirement: AppState holds only the always-on shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)` holding ONLY the always-on resources of the fetch pipeline: a non-optional `settings: AppSettings`, `breakers: AsyncCircuitBreakerFactory`, `proxy_pool: ProxyPool`, and `sqlite: SqliteResource`. The heavy/conditional resources (`browser_backend`, `llm_extractor`, `cookie_jar`) SHALL NOT be fields on `AppState`; they are `Lazy[T]` thunks on `Components` and reach the tool seam unresolved. `AppState` SHALL be constructed only through the single composition root `components.build_components(...)`.

#### Scenario: AppState carries only the always-on resources

- **WHEN** the `AppState` dataclass is inspected
- **THEN** it declares exactly `settings`, `breakers`, `proxy_pool`, and `sqlite`, and declares no `browser_backend` / `llm_extractor` / `cookie_jar` field

#### Scenario: Heavy resources stay off AppState as Lazy thunks

- **WHEN** the resource graph is built via `build_components(...)`
- **THEN** `browser_backend`, `llm_extractor`, and `cookie_jar` are `Lazy[T]` thunks on `Components` (resolved on first await), not attributes of `AppState`

