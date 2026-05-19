## ADDED Requirements

### Requirement: CookieJarResource is registered via app.provide

The system SHALL register `CookieJarResource` via `app.provide(build_cookie_jar)` in `src/a2web/server.py`. The factory SHALL be a named function (not a lambda) with an explicit return annotation, taking `settings: AppSettings` and `sqlite: SqliteResource` as DI kwargs. Insertion order SHALL place the registration AFTER `SqliteResource` (its dependency) and at the same nesting level as `build_browser_pool` and `build_llm_extractor`.

`CookieJarResource` SHALL NOT be a member of `AppState`. It SHALL be surfaced at the tool seam as `Lazy[CookieJarResource]` on tools that may need it (`fetch`, `cookies_refresh`).

#### Scenario: Provider registered

- **WHEN** `from a2web.server import app` is executed
- **THEN** `app.has_provider(CookieJarResource)` returns `True`

#### Scenario: Factory is a named function

- **WHEN** static analysis walks the providers registered on `app`
- **THEN** the factory for `CookieJarResource` is a module-scope function named `build_cookie_jar` with a `-> CookieJarResource` return annotation

#### Scenario: Lazy only — fetch tool seam

- **WHEN** static analysis walks the `fetch` tool's signature
- **THEN** the `cookie_jar` parameter is typed as `Lazy[CookieJarResource]` (not `CookieJarResource`)

#### Scenario: Resource not on AppState

- **WHEN** static analysis walks `AppState`
- **THEN** `AppState` has no `cookie_jar` attribute

### Requirement: CookiesRouter exposes the refresh tool

The system SHALL register a new router class `CookiesRouter` with `slug = "cookies"` and `tools: ClassVar[tuple[Callable, ...]] = (refresh,)`. The router SHALL be attached to the `App` alongside `WebRouter` in `src/a2web/server.py`. The CLI surface SHALL be `a2web cookies refresh`. The MCP tool name SHALL be `refresh` (a2kit v0.39 uses the function name directly; the router slug controls CLI grouping only).

The `cookies_refresh` tool SHALL declare a `cookie_jar: Lazy[CookieJarResource]` kwarg and a `state: AppState` kwarg. Neither SHALL appear in the MCP wire schema.

#### Scenario: CLI group present

- **WHEN** the user runs `a2web --help`
- **THEN** the output lists both `web` and `cookies` subcommand groups

#### Scenario: cookies refresh subcommand present

- **WHEN** the user runs `a2web cookies --help`
- **THEN** the output lists `refresh`

#### Scenario: MCP tool list includes refresh

- **WHEN** an MCP client lists tools from `a2web serve`
- **THEN** the tool list contains both `fetch` and `refresh`

#### Scenario: DI kwargs hidden from wire schema

- **WHEN** an MCP client requests `cookies_refresh`'s input schema
- **THEN** the schema's parameters list is empty (no `state`, no `cookie_jar`)

### Requirement: OperatorHint docstring acknowledges agent-readable code

The `OperatorHint` docstring in `src/a2web/models.py` SHALL be updated to acknowledge that the `code` field is a stable agent-readable branch point. The previous claim that "the AI agent never reads these to decide a next action" SHALL be removed or softened, since existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) are already useful to agents in practice and `cookies_stale` extends this pattern.

The Pydantic schema for `OperatorHint` (field names, types, defaults) SHALL NOT change. Only the docstring is modified.

#### Scenario: Docstring no longer claims agents do not read these

- **WHEN** the docstring of `OperatorHint` is read
- **THEN** it does NOT contain the substring "agent never reads these" (case-insensitive) and DOES acknowledge `code` as a stable agent-readable identifier

#### Scenario: Schema unchanged

- **WHEN** `OperatorHint.model_json_schema()` is compared between the previous release and this change
- **THEN** the schema is identical (field names, types, defaults, requirements)
