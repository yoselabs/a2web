## MODIFIED Requirements

### Requirement: CookieJarResource mirrors a single browser profile into SqliteResource

The system SHALL define `CookieJarResource` in `src/a2web/cookie_jar.py` with `__aenter__` / `__aexit__` lifecycle wrappers, wired in the ONE composition root `components.build_components()` and surfaced at the tool seam as a `Lazy[CookieJarResource]` thunk on the frozen `Components` dataclass. The thunk is constructed on first await and entered via `ResourceScope` (LIFO teardown from the FastMCP lifespan exit). The resource SHALL be domain-coupled (reads `AppSettings`, depends on `SqliteResource`); it SHALL NOT be a member of `AppState`.

The resource SHALL expose `async def refresh() -> RefreshResult`, `async def get_for_host(host: str, scheme: str, path: str) -> list[Cookie]`, and `async def staleness() -> StalenessInfo` where:

- `RefreshResult` carries `profile: str`, `browser: Literal["chrome","firefox"]`, `refreshed_count: int`, `refreshed_at: datetime`.
- `StalenessInfo` carries `last_refresh_at: datetime | None`, `age_hours: float | None`, `is_stale: bool`.

The mirror SHALL live in two tables inside the existing `SqliteResource`:

- `a2web_cookies(profile, browser, host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite)` with `PRIMARY KEY (profile, browser, host_key, name, path)` and an index on `(profile, browser, host_key)`.
- `cookies_meta(profile, browser, last_refresh_at, refreshed_count)` with `PRIMARY KEY (profile, browser)`.

The resource SHALL create the tables on first `__aenter__` if missing (idempotent).

#### Scenario: Resource is wired in the composition root

- **WHEN** `components.build_components(settings=...)` builds the resource graph
- **THEN** `Components.cookie_jar` is a `Lazy[CookieJarResource]` thunk surfaced at the tool seam (constructed on first await, entered via `ResourceScope`), not a DI-container provider lookup

#### Scenario: Resource is not on AppState

- **WHEN** static analysis walks `a2web.state.AppState`
- **THEN** `AppState` has no `cookie_jar` attribute

#### Scenario: Refresh on fresh DB creates rows

- **WHEN** `CookieJarResource.refresh()` is called against a fake reader returning 50 cookies for profile "Default" with browser "chrome"
- **THEN** `a2web_cookies` contains 50 rows for that (profile, browser), `cookies_meta` has exactly one row for ("Default","chrome") with `refreshed_count == 50`, and the returned `RefreshResult.refreshed_count == 50`

#### Scenario: Refresh is atomic replace per profile/browser

- **WHEN** the table already contains 50 rows for ("Default","chrome") and `refresh()` is called with a fake reader returning 30 cookies
- **THEN** after the call `a2web_cookies` contains exactly 30 rows for ("Default","chrome"); rows for other (profile, browser) pairs are unchanged

#### Scenario: get_for_host returns matching cookies

- **WHEN** the mirror contains `(.example.com, sid, value1, /, ...)` and `(other.com, x, value2, /, ...)` and `get_for_host("api.example.com", "https", "/v1/x")` is called
- **THEN** the returned list contains the `.example.com` cookie and not the `other.com` cookie

#### Scenario: get_for_host respects secure flag

- **WHEN** a cookie has `is_secure=1` and the requested scheme is `http`
- **THEN** the cookie is NOT returned

#### Scenario: get_for_host respects path prefix

- **WHEN** a cookie has `path="/admin"` and the requested path is `/public/x`
- **THEN** the cookie is NOT returned

#### Scenario: get_for_host drops expired cookies

- **WHEN** a cookie has `expires_utc` in the past and `get_for_host` is called
- **THEN** the cookie is NOT returned

#### Scenario: Session cookies are kept

- **WHEN** a cookie has `expires_utc = NULL` and host/path/scheme match
- **THEN** the cookie IS returned

#### Scenario: Staleness reports never-refreshed state

- **WHEN** `cookies_meta` has no row for the configured (profile, browser)
- **THEN** `staleness()` returns `last_refresh_at=None`, `age_hours=None`, `is_stale=True`

#### Scenario: Staleness reports fresh state

- **WHEN** `last_refresh_at` is 1 hour ago and `cookie_stale_after_hours=24`
- **THEN** `staleness().is_stale == False` and `0.9 < staleness().age_hours < 1.1`

#### Scenario: Staleness reports stale state

- **WHEN** `last_refresh_at` is 30 hours ago and `cookie_stale_after_hours=24`
- **THEN** `staleness().is_stale == True`

### Requirement: cookies refresh tool

The system SHALL expose a `refresh` MCP tool registered by `routers.register_cookies_tools` with `@mcp.tool(...)`, gated on `expose_cookies_tool` (so the tool is ABSENT — not present-and-failing — on a served a2web with no local browser). The CLI surface SHALL be `a2web cookies refresh`. The tool SHALL accept no arguments (profile and browser come from `AppSettings`) and SHALL return a pydantic model `CookiesRefreshResult(profile, browser, refreshed_count, refreshed_at)` defined at module scope. When `cookie_source == "none"` the tool SHALL return a result with `refreshed_count = 0` and append a notice to a `notes: str` field explaining that cookie source is disabled.

#### Scenario: CLI surface

- **WHEN** the user runs `a2web cookies --help`
- **THEN** the output lists `refresh` as a subcommand

#### Scenario: MCP tool name is `refresh`

- **WHEN** an MCP client lists tools from a served a2web with `expose_cookies_tool` enabled
- **THEN** the tool list includes `refresh` (CLI grouping `a2web cookies refresh`)

#### Scenario: Tool returns module-scope pydantic model

- **WHEN** static analysis walks the tool's return type
- **THEN** the return type is a module-scope pydantic model (NOT a dict, NOT a nested class)

#### Scenario: Refresh with cookie_source=none returns zero count

- **WHEN** `settings.cookie_source == "none"` and `cookies_refresh` is invoked
- **THEN** the result has `refreshed_count == 0` and `notes` contains a message indicating the source is disabled

#### Scenario: Refresh with chrome source returns positive count

- **WHEN** `settings.cookie_source == "chrome"` and the test seam injects a fake reader returning 42 cookies
- **THEN** the result has `refreshed_count == 42`, `profile == settings.cookie_profile`, `browser == "chrome"`, and `refreshed_at` is approximately the current time

### Requirement: Staleness surfaces as OperatorHint and LDD event

The system SHALL, on every fetch where `cookie_source != "none"` AND `staleness().is_stale == True`, append to `FetchResponse.operator_hints` an `OperatorHint` with `code = "cookies_stale"`, a `message` field naming the actual age and threshold, and `fix = "Run \`a2web cookies refresh\`"`. The system SHALL also emit one `CookiesStale(...)` event per fetch in the stale state via `await a2web.log.info(CookiesStale(...))`. The `OperatorHint` and the `CookiesStale` event SHALL NOT appear when cookies are fresh.

#### Scenario: Stale state appends operator hint

- **WHEN** `cookie_source == "chrome"`, `last_refresh_at` is 30 hours ago, threshold is 24 hours, and a fetch completes
- **THEN** `response.operator_hints` contains exactly one entry with `code == "cookies_stale"` whose `message` mentions `30` and `24`, and whose `fix` mentions `a2web cookies refresh`

#### Scenario: Never-refreshed state appends operator hint

- **WHEN** `cookie_source == "chrome"`, `cookies_meta` has no row for the configured profile, and a fetch completes
- **THEN** `response.operator_hints` contains exactly one entry with `code == "cookies_stale"`

#### Scenario: Fresh state appends no hint

- **WHEN** `cookie_source == "chrome"`, `last_refresh_at` is 1 hour ago, threshold is 24 hours
- **THEN** `response.operator_hints` contains no entry with `code == "cookies_stale"` and no `CookiesStale` event is emitted

#### Scenario: cookie_source none appends no hint

- **WHEN** `cookie_source == "none"`, regardless of mirror state
- **THEN** `response.operator_hints` contains no entry with `code == "cookies_stale"` and no `CookiesStale` event is emitted
