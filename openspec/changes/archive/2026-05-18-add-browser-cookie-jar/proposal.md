## Why

Many high-value URLs are gated behind a user's logged-in session (NYT, FT, X/Twitter, Reddit NSFW, LinkedIn) or behind anti-bot challenges that drop dramatically when a request arrives with a real session cookie (Cloudflare clearance). Today a2web fetches with no cookie jar at all — raw tier sends nothing, browser tier keeps per-host cookies warm in-memory but ephemeral. The agent and the human operator both have a fully logged-in Chrome (or Firefox) profile sitting on the same machine; we should be able to use it.

## What Changes

- New opt-in capability: a2web reads cookies from the user's local Chrome (macOS) or Firefox profile, mirrors them into its own SqliteResource, and threads them through raw + browser tiers on every fetch.
- New CLI + MCP tool `a2web cookies refresh` — explicit refresh action; this is the only moment macOS Keychain prompts the user. Fetches read from a2web's own sqlite afterwards, so Chrome can keep running and no per-fetch prompts happen.
- New settings (env + YAML): `cookie_source: Literal["none","chrome","firefox"] = "none"` (opt-in), `cookie_profile: str = "Default"`, `cookie_stale_after_hours: int = 24`.
- Staleness signal: when `cookie_source != "none"` and the mirror is missing or older than `cookie_stale_after_hours`, every fetch response gains `OperatorHint(code="cookies_stale", ...)` so the agent and operator both see it. An LDD event `CookiesStale(profile, age_hours)` is emitted in parallel for observability sinks.
- `OperatorHint` docstring softened: the `code` field is a stable agent-readable branch point. Existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) already serve both audiences; the previous "agents never read these" claim was descriptive of original intent, not a constraint.
- Hand-written readers under `src/a2web/packages/cookie_store/{chrome.py,firefox.py,models.py}` — no third-party cookie library. (Audited `rookiepy` and `browser_cookie3`; both YELLOW on supply-chain axes — dormant single-maintainer projects, no PyPI Trusted Publishing. Our needs on macOS reduce to ~120 lines: sqlite read + `security find-generic-password -wa "Chrome Safe Storage"` + AES-GCM via `cryptography.hazmat`.)
- Promote `cryptography` to a direct dependency (already transitive via curl_cffi).
- Cookie values redacted from LDD event payloads and structlog by default — only names + hosts + counts appear in observability output.

**Out of scope** (deferred): LDD severity levels (separate a2kit feedback item — emit at single level today, swap to `warn` when a2kit supports severity), Camoufox `user_data_dir` profile inheritance, Linux/Windows Chrome (only macOS Chrome v1), multi-profile merge in a single refresh, automatic background refresh, Safari/Edge/Brave/Arc.

## Capabilities

### New Capabilities
- `browser-cookies`: opt-in cookie source that extracts cookies from a local Chrome (macOS) or Firefox profile, mirrors them into a2web's SqliteResource via an explicit refresh action, surfaces staleness via `OperatorHint` + LDD, and threads them through raw + browser tiers on fetch.

### Modified Capabilities
- `raw-tier`: tier now accepts a per-fetch `cookies: dict[str, str]` and passes it to curl_cffi when non-empty. No behavior change when caller passes no cookies.
- `browser-tier`: per-host BrowserContext now seeds `context.add_cookies([...])` from the fetch-scoped cookie set when non-empty. No behavior change when caller passes no cookies.
- `tier-pipeline`: `_phase_tier_loop` gains an early cookie-resolution step that resolves `Lazy[CookieJarResource]` (only when `cookie_source != "none"`), populates `FetchContext.cookies`, and appends the `cookies_stale` OperatorHint when the mirror is missing or past the staleness threshold.
- `app-composition`: new `app.provide(build_cookie_jar)` registration; `fetch` tool signature gains `cookie_jar: Lazy[CookieJarResource]`; new `cookies_refresh` tool exposed by `WebRouter`.

## Impact

- **Code**: new `src/a2web/packages/cookie_store/` package; new `src/a2web/cookie_jar.py`; touch points in `settings.py`, `server.py`, `routers.py`, `state.py` (only for the new resource provider — `CookieJarResource` is NOT on `AppState`, it's surfaced as `Lazy[T]` at the tool seam per project conventions), `fetcher.py` (new tier-loop phase + `FetchContext` field), `models.py` (`OperatorHint` docstring), `tiers/raw.py` + `tiers/browser.py` (consume `FetchContext.cookies`).
- **Dependencies**: `cryptography` promoted from transitive to direct (already present via curl_cffi). No new third-party cookie/extractor library.
- **Storage**: two new tables in the existing SqliteResource — `a2web_cookies` (per-cookie rows) and `cookies_meta` (per-profile last-refresh marker). No migration story needed since SqliteResource is a per-machine cache, not a shared schema.
- **CLI / MCP surface**: new `a2web cookies refresh` command and `cookies_refresh` MCP tool. Existing `fetch` tool signature unchanged from the agent's perspective — cookie wiring is internal.
- **Security**: macOS Keychain prompt appears on every `cookies refresh` invocation (OS-managed; not configurable by a2web). Cookie values redacted from observability output. Mirror sqlite inherits filesystem permissions from `AppSettings.sqlite_path`.
- **Operational**: when `cookie_source` is left at the default `none`, this change is a no-op. Opt-in costs the user one `a2web cookies refresh` per ~24h.
