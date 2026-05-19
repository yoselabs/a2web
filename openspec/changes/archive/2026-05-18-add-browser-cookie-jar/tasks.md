## 1. Settings and dependencies

- [x] 1.1 Add `cookie_source: Literal["none","chrome","firefox"] = "none"`, `cookie_profile: str = "Default"`, `cookie_stale_after_hours: int = 24` to `AppSettings` in `src/a2web/settings.py` with `A2WEB_COOKIE_*` env mapping
- [x] 1.2 Promote `cryptography` from transitive (via curl_cffi) to a direct dependency in `pyproject.toml`; run `uv lock` to refresh `uv.lock`
- [x] 1.3 Update `OperatorHint` docstring in `src/a2web/models.py` to remove the "agents never read these" line and acknowledge `code` as a stable agent-readable identifier; verify schema unchanged via `OperatorHint.model_json_schema()`

## 2. Boundary types and BDD specs (BDD-first)

- [x] 2.1 Add `CookieRow` (slots dataclass) and `ChromeCookieAccessError` to `src/a2web/packages/cookie_store/models.py`
- [x] 2.2 Add `Cookie` (slots dataclass) and `StalenessInfo` (slots dataclass) to `src/a2web/cookie_jar.py` (module-scope types; pydantic only at API boundary for `CookiesRefreshResult`)
- [x] 2.3 Add `CookiesRefreshResult` pydantic model at module scope in `src/a2web/cookie_jar.py`
- [x] 2.4 Add `CookiesStale` LDD event payload type in `src/a2web/events/types.py`; register it via `app.ldd.events.register(CookiesStale)` in `server.py`
- [x] 2.5 Write Gherkin-style spec/fixture stubs for the new `test_cookie_jar.py`, `test_cookies_refresh_tool.py`, `test_fetcher_with_cookies.py` (scenario names only, asserting None initially) — confirms scenario coverage matches the spec before implementation

## 3. Cookie-store package (pure mechanics)

- [x] 3.1 Implement `src/a2web/packages/cookie_store/firefox.py::read_cookies(profile)` — locate `cookies.sqlite` under `~/Library/Application Support/Firefox/Profiles/<profile>/` (resolve `default-release` alias), `cp` to tempdir, read `moz_cookies` rows, normalize into `list[CookieRow]`
- [x] 3.2 Implement `src/a2web/packages/cookie_store/chrome.py::_fetch_keychain_key()` — subprocess `security find-generic-password -wa "Chrome Safe Storage"`, capture stdout, raise `ChromeCookieAccessError` (no secret material in message) on non-zero exit
- [x] 3.3 Implement `chrome.py::_derive_aes_key(password)` — PBKDF2-HMAC-SHA1 with salt `b"saltysalt"`, 1003 iterations, 16-byte key length, via `cryptography.hazmat.primitives.kdf.pbkdf2`
- [x] 3.4 Implement `chrome.py::_decrypt_value(encrypted)` — strip `v10`/`v11` prefix, AES-GCM decrypt via `cryptography.hazmat.primitives.ciphers.aead.AESGCM` using a fixed 12-byte IV `b" " * 12` (Chrome convention) and 16-byte auth tag; return plaintext utf-8; return `""` for empty input
- [x] 3.5 Implement `chrome.py::read_cookies(profile)` — locate Cookies sqlite under `~/Library/Application Support/Google/Chrome/<profile>/`, `cp` to tempdir, SELECT all rows, decrypt where `encrypted_value` non-empty, fall back to plaintext `value` field, normalize into `list[CookieRow]`
- [x] 3.6 Implement `cookie_store/__init__.py::read_cookies(browser, profile)` dispatcher; export `CookieRow`, `ChromeCookieAccessError`
- [x] 3.7 Add `tests/test_cookie_store_firefox.py` — feed a fixture `cookies.sqlite` (created in test setup via raw sqlite3), assert normalized output shape
- [x] 3.8 Add `tests/test_cookie_store_chrome_decrypt.py` — fixture-based: hand-craft a `(salt, password, plaintext) → encrypted_value` round-trip and assert decrypt produces the plaintext. Does NOT touch real Chrome / Keychain.

## 4. CookieJarResource (domain-coupled wiring)

- [x] 4.1 Implement `CookieJarResource.__init__(settings, sqlite)` storing both; lazy `_ensure()` creates `a2web_cookies` and `cookies_meta` tables if missing
- [x] 4.2 Implement `__aenter__` / `__aexit__` as thin wrappers around `_ensure()` / `close()` (close is a no-op for now — sqlite is owned by `SqliteResource`)
- [x] 4.3 Implement `async def refresh()` — call `packages.cookie_store.read_cookies(...)` via `asyncio.to_thread`, run an atomic `DELETE WHERE profile/browser` + bulk `INSERT` + `INSERT OR REPLACE INTO cookies_meta` transaction, return `RefreshResult`
- [x] 4.4 Implement `async def get_for_host(host, scheme, path)` — query `a2web_cookies` filtered by domain match (host or `.suffix`), path prefix, secure flag, expiry; return `list[Cookie]`
- [x] 4.5 Implement `async def staleness()` — read `cookies_meta` for configured (profile, browser); return `StalenessInfo(last_refresh_at, age_hours, is_stale)`
- [x] 4.6 Implement `build_cookie_jar(settings, sqlite) -> CookieJarResource` named factory with explicit return annotation
- [x] 4.7 Add `tests/test_cookie_jar.py` covering scenarios from `specs/browser-cookies/spec.md` (resource lifecycle, atomic refresh, domain matching, secure flag, path prefix, expiry, session cookies, staleness states)

## 5. App composition

- [x] 5.1 Register `CookieJarResource` via `app.provide(build_cookie_jar)` in `src/a2web/server.py`, AFTER `SqliteResource` and at the same nesting level as `build_browser_pool` / `build_llm_extractor`
- [x] 5.2 Confirm `CookieJarResource` is NOT added to `AppState` (no changes to `state.py`)
- [x] 5.3 Implement `cookies_refresh` tool function in `src/a2web/cookie_jar.py` (or `routers.py`) with `Annotated[...]` arg metadata; declare `cookie_jar: Lazy[CookieJarResource]` and `state: AppState` DI kwargs; handle `cookie_source == "none"` case (return zero count + notes)
- [x] 5.4 Define `CookiesRouter` class with `slug = "cookies"`, `tools = (cookies_refresh,)` ClassVar in `src/a2web/routers.py`
- [x] 5.5 Attach `CookiesRouter` to the App in `server.py` alongside `WebRouter`
- [x] 5.6 Add `tests/test_cookies_refresh_tool.py` — use `a2kit.testing.client(app)` + `client.override(CookieJarResource, FakeJar(...))`; assert (a) `cookie_source=none` returns zero count with notes, (b) chrome source with fake reader returns 42, updates meta, (c) tool not visible at `state`/`cookie_jar` in wire schema

## 6. FetchContext and orchestrator wiring

- [x] 6.1 Add `cookies: dict[str, str]` and `cookies_full: list[Cookie]` fields to `FetchContext` in `src/a2web/fetcher.py` (default empty)
- [x] 6.2 Add `cookie_jar: Lazy[CookieJarResource]` kwarg to the `fetch` tool signature in `src/a2web/routers.py`; thread it into the orchestrator
- [x] 6.3 Add `_phase_resolve_cookies(ctx)` helper in `fetcher.py` — when `settings.cookie_source != "none"`: resolve `Lazy`, call `get_for_host`, populate `ctx.cookies` (name→value) and `ctx.cookies_full` (full Cookie list); emit a `CookiesAttached` LDD event with redacted payload (names + host + count, no values)
- [x] 6.4 Call `_phase_resolve_cookies` at the top of `_phase_tier_loop` and again after any `RewriteUrl` restart
- [x] 6.5 Add `_phase_cookies_staleness(ctx, response)` helper — when `settings.cookie_source != "none"` and `staleness().is_stale`: append a single `OperatorHint(code="cookies_stale", message=..., fix=...)` to `response.operator_hints` (guarded by an idempotency flag on `ctx`); emit one `CookiesStale` LDD event; called once at fetch end
- [x] 6.6 Pass `ctx.cookies` to raw tier dispatch as the new `cookies=` kwarg; pass `ctx.cookies_full` to browser tier dispatch as the new `cookies_full=` kwarg; jina tier dispatch unchanged (no cookies)
- [x] 6.7 Add `tests/test_fetcher_with_cookies.py` — three scenarios: (a) `cookie_source=none` → no cookies attached, no hint; (b) chrome with fresh mirror → raw tier receives cookies dict, browser tier receives Playwright-shaped list, no hint; (c) chrome with stale mirror → cookies attached AND hint present with `code="cookies_stale"` exactly once

## 7. Tier touch-ups

- [x] 7.1 Add `cookies: dict[str, str] | None = None` kwarg to `RawTier.fetch`; pass to `curl_cffi.requests.get(cookies=...)` when truthy; never log values
- [x] 7.2 Add `cookies_full: list[Cookie] | None = None` kwarg to `BrowserTier.fetch`; convert to Playwright shape via a helper in `packages/cookie_store/__init__.py` (or local) and call `context.add_cookies([...])` BEFORE `page.goto(url)` when truthy; never log values
- [x] 7.3 Verify `JinaTier.fetch` is unchanged — no cookies kwarg, no per-tier wiring
- [x] 7.4 Add tier-level unit tests for raw + browser cookie pass-through (scenarios from `specs/raw-tier/spec.md` and `specs/browser-tier/spec.md`)

## 8. Redaction and observability

- [x] 8.1 Add `redact_cookie_for_event(cookie)` helper that returns `{name, host_key, path, value_length}` (no value) — used by every LDD event payload that mentions cookies
- [x] 8.2 Ensure structlog `bind_contextvars` calls around cookie attach steps include only counts/names/hosts, never values
- [x] 8.3 Add `tests/test_cookie_redaction.py` — assert no cookie value appears in any captured LDD event, structlog record, or diagnostic row across the three fetch scenarios

## 9. Documentation

- [x] 9.1 Update `CLAUDE.md` Architecture section with the cookie-jar seam, the `CookiesRouter`, and the redaction discipline
- [x] 9.2 Update `CHANGELOG.md` with the new opt-in cookie feature, settings, CLI/MCP surface, and security posture (no third-party cookie library; `cryptography` promoted to direct)
- [x] 9.3 Add a short "Cookies" section to README explaining opt-in usage, the refresh flow, the staleness signal, and the macOS-only Chrome support

## 10. Packages-independence + final gate

- [x] 10.1 Run `tests/test_packages_independence.py` and confirm `packages/cookie_store/*` does not import from `a2web.<domain>`
- [x] 10.2 Run `make lint` and fix
- [x] 10.3 Run `make ty` and fix
- [x] 10.4 Run `make test` and confirm coverage ≥85%
- [ ] 10.5 Manual smoke on Denis's machine: `a2web cookies refresh` (one Keychain prompt expected), then `a2web web fetch --url=...` against an auth-gated site and confirm cookies arrive at the upstream (requires human + real Chrome — left unchecked)
- [x] 10.6 Open feedback item to a2kit: "LDD severity levels — add `level` field to event payloads, sink-side filter" in `docs/history/A2KIT_FEEDBACK_v0.40+.md` (or current feedback round)
