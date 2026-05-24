# browser-cookies Specification

## Purpose
TBD - created by archiving change add-browser-cookie-jar. Update Purpose after archive.
## Requirements
### Requirement: Opt-in cookie source via settings

The system SHALL expose three `AppSettings` fields: `cookie_source: Literal["none","chrome","chromium","brave","edge","firefox","safari","vivaldi","opera","opera_gx"]` (default `"none"`), `cookie_profile: str` (default `"Default"`), `cookie_stale_after_hours: int` (default `24`). When `cookie_source == "none"` the cookie subsystem SHALL be inert — no resource construction, no DB access, no observable behavior change vs. the prior release. The widened Literal SHALL accept the same `"chrome"` and `"firefox"` values as the v0.8 release with identical observable behavior.

#### Scenario: Default settings are inert

- **WHEN** `AppSettings()` is constructed with no env vars and no YAML
- **THEN** `settings.cookie_source == "none"`, `settings.cookie_profile == "Default"`, `settings.cookie_stale_after_hours == 24`

#### Scenario: Env var enables Chrome source

- **WHEN** `A2WEB_COOKIE_SOURCE=chrome` is set in the environment
- **THEN** `AppSettings().cookie_source == "chrome"`

#### Scenario: Env var enables Brave source

- **WHEN** `A2WEB_COOKIE_SOURCE=brave` is set in the environment
- **THEN** `AppSettings().cookie_source == "brave"`

#### Scenario: YAML overrides default profile

- **WHEN** the YAML config sets `cookie_profile: "Work"` and env vars are unset
- **THEN** `AppSettings().cookie_profile == "Work"`

#### Scenario: Inert when source is none

- **WHEN** `cookie_source == "none"` and a fetch executes
- **THEN** the fetch SHALL NOT resolve `CookieJarResource`, SHALL NOT touch `a2web_cookies`/`cookies_meta`, SHALL NOT emit cookie-related LDD events, and SHALL NOT append a `cookies_stale` operator hint

#### Scenario: Unknown cookie_source value fails validation

- **WHEN** `A2WEB_COOKIE_SOURCE=safari_beta` (not in the Literal) is set
- **THEN** `AppSettings()` raises `pydantic.ValidationError` at construction time

### Requirement: CookieJarResource mirrors a single browser profile into SqliteResource

The system SHALL define `CookieJarResource` in `src/a2web/cookie_jar.py` as an a2kit-managed resource with `__aenter__` / `__aexit__` lifecycle wrappers, registered via `app.provide(build_cookie_jar)` and surfaced at the tool seam as `Lazy[CookieJarResource]`. The resource SHALL be domain-coupled (reads `AppSettings`, depends on `SqliteResource`); it SHALL NOT be a member of `AppState`.

The resource SHALL expose `async def refresh() -> RefreshResult`, `async def get_for_host(host: str, scheme: str, path: str) -> list[Cookie]`, and `async def staleness() -> StalenessInfo` where:

- `RefreshResult` carries `profile: str`, `browser: Literal["chrome","firefox"]`, `refreshed_count: int`, `refreshed_at: datetime`.
- `StalenessInfo` carries `last_refresh_at: datetime | None`, `age_hours: float | None`, `is_stale: bool`.

The mirror SHALL live in two tables inside the existing `SqliteResource`:

- `a2web_cookies(profile, browser, host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite)` with `PRIMARY KEY (profile, browser, host_key, name, path)` and an index on `(profile, browser, host_key)`.
- `cookies_meta(profile, browser, last_refresh_at, refreshed_count)` with `PRIMARY KEY (profile, browser)`.

The resource SHALL create the tables on first `__aenter__` if missing (idempotent).

#### Scenario: Resource is registered via app.provide

- **WHEN** `from a2web.server import app` is executed
- **THEN** `app.has_provider(CookieJarResource)` returns `True`

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

The system SHALL expose a `refresh` MCP tool decorated `@a2kit.write` (or appropriate write decorator) on a new `CookiesRouter` with `slug = "cookies"` and `tools = (refresh,)`. The CLI surface SHALL be `a2web cookies refresh`. (a2kit v0.39 derives the MCP tool name from the function name; the router slug controls CLI grouping only.) The tool SHALL accept no arguments (profile and browser come from `AppSettings`) and SHALL return a pydantic model `CookiesRefreshResult(profile, browser, refreshed_count, refreshed_at)` defined at module scope. When `cookie_source == "none"` the tool SHALL return a result with `refreshed_count = 0` and append a notice to a `notes: str` field explaining that cookie source is disabled.

#### Scenario: CLI surface

- **WHEN** the user runs `a2web cookies --help`
- **THEN** the output lists `refresh` as a subcommand

#### Scenario: MCP tool name is `refresh`

- **WHEN** an MCP client lists tools from `a2web serve`
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

### Requirement: Cookie-store packages are domain-pure

The system SHALL place all browser-specific cookie reading and decryption under `src/a2web/packages/cookie_store/` with no imports from `a2web.<domain>`. The package SHALL expose `read_cookies(browser: Literal["chrome","firefox"], profile: str) -> list[CookieRow]` returning a typed dataclass (NOT a `dict[str, Any]`). The Chrome reader SHALL live in `chrome.py`, the Firefox reader in `firefox.py`, and the boundary types in `models.py`.

#### Scenario: Packages-independence invariant holds

- **WHEN** `tests/test_packages_independence.py` walks every `.py` under `packages/`
- **THEN** no file under `packages/cookie_store/` imports from `a2web.<domain>` modules (settings, state, models, fetcher, tiers, handlers, routers, server, cookie_jar)

#### Scenario: CookieRow is a typed dataclass

- **WHEN** static analysis walks `packages.cookie_store.models`
- **THEN** `CookieRow` is a `@dataclass(slots=True)` with explicit fields (host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite), NOT a `dict[str, Any]` bag

### Requirement: Cookies wire into raw and browser tiers; jina skips

The system SHALL thread the per-fetch cookie set into the raw tier as a `cookies: dict[str, str]` kwarg passed to `curl_cffi.requests.get` and into the browser tier via `context.add_cookies([...])` after Playwright shape conversion (`is_httponly` → `httpOnly`, `samesite` → `sameSite` with case normalization). The jina tier SHALL NOT receive cookies — its remote reader (`r.jina.ai`) would leak the session to a third party.

#### Scenario: Raw tier receives cookies

- **WHEN** a fetch executes the raw tier with a non-empty `FetchContext.cookies = {"sid": "x", "csrf": "y"}`
- **THEN** the captured `curl_cffi.requests.get` call has `cookies == {"sid": "x", "csrf": "y"}`

#### Scenario: Browser tier seeds context cookies

- **WHEN** a fetch executes the browser tier with non-empty `FetchContext.cookies_full` (full Cookie objects)
- **THEN** the BrowserContext's `add_cookies` is invoked once with a list whose `name`, `value`, `domain`, `path`, `secure`, `httpOnly`, `sameSite` fields match the source cookies

#### Scenario: Jina tier ignores cookies

- **WHEN** a fetch executes the jina tier with non-empty `FetchContext.cookies`
- **THEN** the captured outbound request to `r.jina.ai` contains no Cookie header and no cookies kwarg

### Requirement: Staleness surfaces as OperatorHint and LDD event

The system SHALL, on every fetch where `cookie_source != "none"` AND `staleness().is_stale == True`, append to `FetchResponse.operator_hints` an `OperatorHint` with `code = "cookies_stale"`, a `message` field naming the actual age and threshold, and `fix = "Run \`a2web cookies refresh\`"`. The system SHALL also emit one `a2kit.ldd.event(CookiesStale(...))` per fetch in the stale state. The `OperatorHint` and the LDD event SHALL NOT appear when cookies are fresh.

#### Scenario: Stale state appends operator hint

- **WHEN** `cookie_source == "chrome"`, `last_refresh_at` is 30 hours ago, threshold is 24 hours, and a fetch completes
- **THEN** `response.operator_hints` contains exactly one entry with `code == "cookies_stale"` whose `message` mentions `30` and `24`, and whose `fix` mentions `a2web cookies refresh`

#### Scenario: Never-refreshed state appends operator hint

- **WHEN** `cookie_source == "chrome"`, `cookies_meta` has no row for the configured profile, and a fetch completes
- **THEN** `response.operator_hints` contains exactly one entry with `code == "cookies_stale"`

#### Scenario: Fresh state appends no hint

- **WHEN** `cookie_source == "chrome"`, `last_refresh_at` is 1 hour ago, threshold is 24 hours
- **THEN** `response.operator_hints` contains no entry with `code == "cookies_stale"` and no `CookiesStale` LDD event is emitted

#### Scenario: cookie_source none appends no hint

- **WHEN** `cookie_source == "none"`, regardless of mirror state
- **THEN** `response.operator_hints` contains no entry with `code == "cookies_stale"` and no `CookiesStale` LDD event is emitted

### Requirement: Cookie values are redacted from LDD and structlog

The system SHALL NOT emit decrypted cookie values into any LDD event payload or `structlog` record. Event payloads SHALL carry counts, host_keys, and cookie names only; the `value` field SHALL be replaced by a redaction marker (e.g., `"<redacted:N>"` where `N` is the value length, or omitted entirely).

#### Scenario: LDD event payload contains no values

- **WHEN** a fetch with cookies emits a `CookiesAttached` (or equivalent) LDD event for 3 cookies
- **THEN** the captured event payload contains the 3 cookie names and the host, and does NOT contain any cookie value substring

#### Scenario: Structlog binding contains no values

- **WHEN** a fetch with cookies binds context for structlog around the cookie attach step
- **THEN** the captured log record's bound context contains no cookie value

### Requirement: Browser cookies are extracted via browser-cookie3 adapter

The system SHALL extract browser cookies through a thin adapter (`src/a2web/packages/cookie_store/store.py`) that delegates to `browser_cookie3.<source>(cookie_file=..., domain_name=...)` based on `settings.cookie_source`. The adapter SHALL convert the returned `http.cookiejar.CookieJar` into `list[Cookie]` using the existing `Cookie` boundary dataclass in `packages/cookie_store/models.py`.

The adapter SHALL raise a single typed exception (`CookieAccessError`) when the browser profile is missing, when the OS-keystore unlock fails (user denied prompt, keychain locked, item not found), or when `browser-cookie3` raises any underlying error. The exception message SHALL NOT contain any decrypted cookie value or any key material; the original library exception SHALL be attached via `__cause__` for debugging.

The adapter SHALL be a domain-pure module — zero imports from `a2web.<domain>`. The `tests/test_packages_independence.py` invariant continues to enforce this.

#### Scenario: Chrome source on macOS produces cookies

- **WHEN** `cookie_source = "chrome"` and `browser_cookie3.chrome()` returns a `CookieJar` with one cookie
- **THEN** the adapter returns a list of one `Cookie` with the same name/value/host/path/expiry/secure/httponly/samesite

#### Scenario: Brave source on Linux produces cookies

- **WHEN** `cookie_source = "brave"` and `browser_cookie3.brave()` returns a `CookieJar` with cookies
- **THEN** the adapter returns the equivalent `list[Cookie]`

#### Scenario: Missing profile raises typed error

- **WHEN** the adapter is invoked against a profile whose path browser-cookie3 cannot locate
- **THEN** the adapter raises `CookieAccessError` whose message names the source and contains no secret material; `__cause__` is set to the underlying library exception

#### Scenario: Keychain prompt denied raises typed error

- **WHEN** `browser_cookie3.chrome()` raises because the user denied the macOS Keychain prompt
- **THEN** the adapter raises `CookieAccessError` and does NOT propagate the bare library exception

#### Scenario: Adapter does not import a2web domain modules

- **WHEN** `python -c "import ast; from pathlib import Path; ..."` walks `src/a2web/packages/cookie_store/` for AST `Import` / `ImportFrom` nodes
- **THEN** zero imports of any `a2web.<domain>` module are found (matches `tests/test_packages_independence.py`)

### Requirement: Keychain prompt fires only on cookies_refresh

The system SHALL invoke `browser-cookie3` exclusively from within the `cookies_refresh` tool's code path. `CookieJarResource.__aenter__` SHALL NOT call into the adapter; `get_for_host()` SHALL read only from the `a2web_cookies` SQLite mirror; no background timer / startup hook SHALL trigger a refresh.

#### Scenario: Resource enter does not trigger browser-cookie3

- **WHEN** `CookieJarResource.__aenter__()` runs (e.g., when the resource first resolves during a fetch)
- **THEN** `browser_cookie3.<source>()` is NOT called; no Keychain / gnome-keyring / DPAPI prompt fires

#### Scenario: Fetch path reads only from mirror

- **WHEN** a fetch resolves `Lazy[CookieJarResource]` and calls `get_for_host("reddit.com", ...)`
- **THEN** the data source is the `a2web_cookies` table; `browser_cookie3` is not invoked

#### Scenario: cookies_refresh is the only invocation site

- **WHEN** `grep -rn "browser_cookie3" src/a2web/` runs over the source tree
- **THEN** all matches are inside the adapter (`packages/cookie_store/store.py`) and the adapter is only called from the `cookies_refresh` code path in `cookie_jar.py::refresh()`

