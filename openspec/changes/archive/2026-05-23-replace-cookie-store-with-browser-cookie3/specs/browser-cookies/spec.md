## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Chrome reader on macOS decrypts via security CLI + AES-GCM

**Reason**: The macOS-specific Chrome reader is replaced by `browser-cookie3`, which handles Chrome on macOS / Linux / Windows uniformly (Keychain / gnome-keyring / DPAPI under one API). The decryption-mechanism scenarios that pinned to `security find-generic-password` + PBKDF2-HMAC-SHA1 + AES-GCM are no longer testable assertions of a2web's own code.

**Migration**: Behavior is preserved at the observable layer — `cookies_refresh` against `cookie_source == "chrome"` continues to mirror the user's Chrome cookies into `a2web_cookies`. The new `Requirement: Browser cookies are extracted via browser-cookie3 adapter` below covers the contract from the user's perspective. Implementations needing the typed `ChromeCookieAccessError` MUST migrate to catching the broader `CookieAccessError` raised by the adapter.

### Requirement: Firefox reader reads plaintext cookies sqlite

**Reason**: The Firefox reader is replaced by `browser-cookie3`, which reads `cookies.sqlite` across all supported OSes. The "reader copies sqlite to temp dir to avoid lock contention" and "profile-alias resolution" implementation details are now upstream concerns, not a2web spec assertions.

**Migration**: Behavior is preserved — `cookies_refresh` against `cookie_source == "firefox"` continues to mirror the user's Firefox cookies into `a2web_cookies`. The new `Requirement: Browser cookies are extracted via browser-cookie3 adapter` covers the cross-source contract.

## ADDED Requirements

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
