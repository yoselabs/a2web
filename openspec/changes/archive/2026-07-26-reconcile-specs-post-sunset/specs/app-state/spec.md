## ADDED Requirements

### Requirement: AppState holds only the always-on shared resources

The system SHALL define `AppState` in `src/a2web/state.py` as `@dataclass(slots=True)` holding ONLY the always-on resources of the fetch pipeline: a non-optional `settings: AppSettings`, `breakers: AsyncCircuitBreakerFactory`, `proxy_pool: ProxyPool`, and `sqlite: SqliteResource`. The heavy/conditional resources (`browser_backend`, `llm_extractor`, `cookie_jar`) SHALL NOT be fields on `AppState`; they are `Lazy[T]` thunks on `Components` and reach the tool seam unresolved. `AppState` SHALL be constructed only through the single composition root `components.build_components(...)`.

#### Scenario: AppState carries only the always-on resources

- **WHEN** the `AppState` dataclass is inspected
- **THEN** it declares exactly `settings`, `breakers`, `proxy_pool`, and `sqlite`, and declares no `browser_backend` / `llm_extractor` / `cookie_jar` field

#### Scenario: Heavy resources stay off AppState as Lazy thunks

- **WHEN** the resource graph is built via `build_components(...)`
- **THEN** `browser_backend`, `llm_extractor`, and `cookie_jar` are `Lazy[T]` thunks on `Components` (resolved on first await), not attributes of `AppState`

## REMOVED Requirements

### Requirement: AppState is a dataclass holding shared resources

**Reason**: The base requirement was a PR4-era stub: it declared `log_writer`
and `browser_pool` placeholder fields, `sqlite`/`proxy_pool` defaulting to `None`,
and scenarios keyed on `register_state(app)` and "PR4"/"PR7" phasing — all a2kit
composition-era machinery, retired by `sunset-a2kit-dependency`. The live
`AppState` holds only the four always-on resources and is built by the one
composition root.

**Migration**: Replaced by the ADDED requirement "AppState holds only the
always-on shared resources", which declares the current shape (`settings` /
`breakers` / `proxy_pool` / `sqlite`); the single-composition-root construction
guarantee is owned by the `app-composition` requirement "A single composition root
builds every long-lived resource".

### Requirement: Per-App singleton registration

**Reason**: Described the a2kit `register_state(app, *, settings=None)` DI-provider
helper, per-`App` singleton resolution, and an `atexit` sqlite-close hook — all
retired with the framework. Resources are now wired in the one composition root
`components.build_components(...)`; teardown is LIFO via `scope.ResourceScope`
from the FastMCP `lifespan=` exit, not `atexit`.

**Migration**: The single-construction and dependency-safe-teardown guarantees are
owned by the `app-composition` requirements "A single composition root builds
every long-lived resource" and "Resources are torn down in reverse construction
order".

### Requirement: fetch tool resolves AppState via DI

**Reason**: A PR2-era stub: it described a `WebRouter.fetch` tool returning
`tier="stub"` and receiving `state: AppState` as an a2kit DI-injected kwarg. The
`WebRouter` class and DI kwarg injection are gone; there is no `fetch` stub tool
(the surface is `query`/`fetch_raw`, plain closures over `Components`).

**Migration**: Direct tool registration and the wire/injected split are owned by
the `app-composition` requirements "Tools are registered directly" and "A tool's
wire parameters are declared explicitly in its signature"; the live tool contracts
live in `ask-response` and `extraction`.

### Requirement: Server composition registers AppState

**Reason**: Described `src/a2web/server.py` calling `register_state(app)` after
`add_router(WebRouter())` on an a2kit `App`, and a `has_provider(AppState)`
assertion — the a2kit composition idiom, retired. The server is now built by
`server.build_mcp_server(...)` over `fastmcp.FastMCP`.

**Migration**: Server composition is owned by the `app-composition` requirements
"The app composes on the MCP server library directly" and "A single composition
root builds every long-lived resource".
