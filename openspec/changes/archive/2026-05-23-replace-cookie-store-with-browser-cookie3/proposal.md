## Why

The hand-rolled `src/a2web/packages/cookie_store/{chrome,firefox,models}.py` (~375 LoC) reimplements browser cookie extraction that the single-mission `browser-cookie3` library already handles for 8+ browsers across macOS / Linux / Windows. Today a2web supports only Chrome-on-macOS + Firefox-cross-platform; the rest of the matrix is hand-written stubs waiting for time we never spend. Adopting `browser-cookie3` shrinks the package to a thin adapter, unlocks Brave / Edge / Vivaldi / Opera / Safari and the two missing platforms, and removes our exposure to Chrome storage-format changes (which we'd otherwise have to chase by hand).

## What Changes

- Replace internal Chrome reader (`security` CLI + AES via `cryptography`) and Firefox reader (raw `cookies.sqlite` query) with calls into `browser_cookie3.chrome(...)` / `browser_cookie3.firefox(...)` (and the other browsers it covers).
- Collapse `chrome.py` (191 LoC) + `firefox.py` (100 LoC) into a single adapter (`store.py`, ~80 LoC) that converts `http.cookiejar.CookieJar` → our existing `Cookie` boundary dataclass.
- Extend `cookie_source: Literal[...]` to the full set browser-cookie3 supports — `"chrome" | "chromium" | "brave" | "edge" | "firefox" | "safari" | "vivaldi" | "opera" | "opera_gx"` (default still `"none"`).
- Add `browser-cookie3>=0.20,<1` and accept `pycryptodome` as a transitive dep coexisting with `cryptography`.
- Preserve the v0.8 "Keychain prompt only on `cookies_refresh`" UX, the `CookieJarResource` lifecycle / `__aenter__` / `__aexit__` shape, the `CookiesRouter(slug="cookies")` MCP surface, the `cookies_refresh` tool, the `redact_cookie_for_event` redaction path, the `cookies_stale` `OperatorHint`, and the `CookiesStale` LDD event.
- Keep all sync cookie I/O behind the existing `asyncio.to_thread` chokepoint — no async story change.

Not changing: the `a2web_cookies` / `cookies_meta` schema, the `CookieJarResource` provider registration in `server.py`, or any tool / wire-format surface.

## Capabilities

### New Capabilities

None — pure refactor.

### Modified Capabilities

- `browser-cookies`: the requirement set that enumerates `cookie_source` values expands beyond `chrome | firefox`. The "Chrome reader implementation" requirements that pin behavior to the macOS `security` CLI / Chrome AES paths are replaced by ones that delegate to `browser-cookie3` and assert observable behavior (we mirror the user's selected browser/profile into the SqliteResource) rather than the internal mechanism. Scenarios under "inert when source is none", "stale-cookie operator hint", "redaction in LDD events", and "Keychain prompt only on refresh" remain unchanged.

## Impact

- **Code**: `src/a2web/packages/cookie_store/{chrome,firefox}.py` deleted; `src/a2web/packages/cookie_store/store.py` (new, thin adapter) replaces them. `models.py` and `__init__.py` keep their boundary roles. Net ~290 LoC out.
- **Dependencies**: `+browser-cookie3` (direct), `+pycryptodome` (transitive). `cryptography` stays — used by curl_cffi and elsewhere.
- **Settings**: `AppSettings.cookie_source` `Literal[...]` widens. Existing env / YAML for `chrome` and `firefox` continue to work unchanged; new values become valid.
- **Tests**: existing `tests/test_packages_cookie_store_*.py` rewrites against the adapter surface; the `packages/` independence invariant (`tests/test_packages_independence.py`) continues to pass — `browser-cookie3` is third-party, not an `a2web.<domain>` import.
- **Platforms**: macOS keeps working; Linux + Windows become real instead of stub.
- **UX**: zero change for the common path (`A2WEB_COOKIE_SOURCE=chrome` still works the same way). Linux users gain a working `chrome` source for the first time.
- **MCP wire surface**: no change. `CookiesRouter` tool signatures and `OperatorHint(code="cookies_stale")` semantics preserved.
