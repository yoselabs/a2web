## ADDED Requirements

### Requirement: Cookie resolution phase precedes the tier loop

The orchestrator SHALL, when `settings.cookie_source != "none"`, resolve the `Lazy[CookieJarResource]` once per fetch BEFORE entering the tier loop, call `get_for_host(host, scheme, path)` for the request URL, and populate two fields on `FetchContext`:

- `cookies: dict[str, str]` — name→value mapping used by raw tier
- `cookies_full: list[Cookie]` — full Cookie objects used by browser tier

Each subsequent tier dispatch SHALL pass the appropriate field as the tier's `cookies` / `cookies_full` kwarg. When `cookie_source == "none"`, neither field SHALL be populated (both default to empty); `Lazy[CookieJarResource]` SHALL NOT be resolved (lazy-first-use preserved).

When the configured URL is rewritten via `RewriteUrl` and the tier loop restarts, cookies SHALL be re-resolved for the new host BEFORE the next tier dispatch.

#### Scenario: Cookie resolution skipped when source is none

- **WHEN** a fetch runs with `cookie_source == "none"`
- **THEN** `CookieJarResource` is not resolved (its `Lazy` thunk remains unevaluated), and `FetchContext.cookies` is the empty dict

#### Scenario: Cookie resolution runs once per fetch

- **WHEN** a fetch runs with `cookie_source == "chrome"` and dispatches both raw and browser tiers
- **THEN** `CookieJarResource.get_for_host` is called exactly once for the original URL's host (rewrite scenarios are separate)

#### Scenario: Cookies re-resolved after URL rewrite

- **WHEN** a fetch starts at `https://example.com/x`, an after-tier action rewrites to `https://other.com/y`, and the tier loop restarts
- **THEN** `CookieJarResource.get_for_host` is called a second time for `other.com`, and the cookies attached to the next tier dispatch correspond to `other.com`

#### Scenario: Empty cookie set produces empty FetchContext fields

- **WHEN** `cookie_source == "chrome"` and `get_for_host` returns `[]` for the host
- **THEN** `FetchContext.cookies == {}` and `FetchContext.cookies_full == []`, and tiers receive no cookies

### Requirement: Stale-cookies operator hint appended exactly once per stale fetch

The orchestrator SHALL consult `CookieJarResource.staleness()` once per fetch when `cookie_source != "none"`. When `staleness().is_stale == True`, the orchestrator SHALL append a single `OperatorHint(code="cookies_stale", message=..., fix="Run `a2web cookies refresh`")` to `FetchResponse.operator_hints` and emit one `a2kit.ldd.event(CookiesStale(profile, browser, age_hours))` for the fetch.

The hint SHALL NOT be appended more than once per fetch even when the tier loop restarts via `RewriteUrl`. The hint SHALL NOT be appended when `cookie_source == "none"`.

The message SHALL include the numeric `age_hours` (or `"never"` if `last_refresh_at is None`) and the configured `cookie_stale_after_hours` threshold so the agent can reason about the gap.

#### Scenario: Stale hint appended once

- **WHEN** a fetch runs stale and the tier loop restarts via `RewriteUrl`
- **THEN** `response.operator_hints` contains exactly one `code == "cookies_stale"` entry

#### Scenario: Never-refreshed message says "never"

- **WHEN** `staleness().last_refresh_at is None` and a fetch completes
- **THEN** the `cookies_stale` hint's `message` field contains the substring `"never"`

#### Scenario: Stale message names age and threshold

- **WHEN** `staleness().age_hours == 72` and `cookie_stale_after_hours == 24`
- **THEN** the `cookies_stale` hint's `message` contains both `"72"` and `"24"`

#### Scenario: No hint when source disabled

- **WHEN** `cookie_source == "none"`
- **THEN** `response.operator_hints` contains no `cookies_stale` entry and `CookiesStale` is not emitted
