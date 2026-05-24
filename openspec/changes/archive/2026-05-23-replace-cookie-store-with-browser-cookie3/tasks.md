## 1. Dependency + settings

- [ ] 1.1 Add `browser-cookie3>=0.20,<1` to `pyproject.toml` `[project] dependencies`. Run `uv lock` to bring in `pycryptodome` transitively. Confirm no lockfile resolution conflict with existing `cryptography`.
- [ ] 1.2 Widen `AppSettings.cookie_source` Literal in `src/a2web/settings.py` to `Literal["none","chrome","chromium","brave","edge","firefox","safari","vivaldi","opera","opera_gx"]`. Confirm existing `"chrome"` / `"firefox"` env / YAML continues to parse.
- [ ] 1.3 Add a pydantic-settings round-trip test that an unknown value (e.g. `"safari_beta"`) raises `ValidationError`.

## 2. Adapter

- [ ] 2.1 Create `src/a2web/packages/cookie_store/store.py`. Implement `read_cookies(source: CookieSource, *, profile: str | None, domain: str | None = None) -> list[Cookie]`. Map each `CookieSource` Literal value to the corresponding `browser_cookie3.<name>` callable via a frozen dispatch dict.
- [ ] 2.2 Implement `class CookieAccessError(Exception)`. Wrap every `browser_cookie3` call in a try/except that re-raises as `CookieAccessError`, sets `__cause__`, and ensures the message never contains cookie values or key material.
- [ ] 2.3 Convert `http.cookiejar.CookieJar` → `list[Cookie]` (using the existing `Cookie` dataclass in `packages/cookie_store/models.py`). Normalize `expires=None` / `expires=0` semantics; map `version`/`secure`/`httponly`/`samesite` to our boundary fields.
- [ ] 2.4 Document the per-browser `profile` → `cookie_file` resolution in the module docstring. Defer to `browser-cookie3`'s default when `profile` is `"Default"` (no override).

## 3. Domain wiring

- [ ] 3.1 Update `src/a2web/cookie_jar.py::refresh()` to call `store.read_cookies(...)` (via `asyncio.to_thread`) instead of the deleted `chrome.read(...)` / `firefox.read(...)` paths.
- [ ] 3.2 Confirm `CookieJarResource.__aenter__` does NOT call into the adapter. Confirm `get_for_host()` reads only from the SqliteResource-backed `a2web_cookies` mirror.
- [ ] 3.3 Add an assertion test: monkeypatch every `browser_cookie3.<name>` to raise if called, then call `CookieJarResource.__aenter__` + `get_for_host()` and verify the patched functions are never invoked.

## 4. Delete old readers

- [ ] 4.1 Delete `src/a2web/packages/cookie_store/chrome.py`.
- [ ] 4.2 Delete `src/a2web/packages/cookie_store/firefox.py`.
- [ ] 4.3 Update `src/a2web/packages/cookie_store/__init__.py` re-exports: drop `chrome` / `firefox` submodule re-exports; add `store` re-exports (`read_cookies`, `CookieAccessError`, `CookieSource`).
- [ ] 4.4 Grep the source tree for stray imports of `from .chrome` / `from .firefox` and fix.

## 5. Tests

- [ ] 5.1 Replace `tests/test_packages_cookie_store_chrome.py` and `..._firefox.py` with `tests/test_packages_cookie_store_store.py`. Use monkeypatched `browser_cookie3.<name>` fakes returning a stub `http.cookiejar.CookieJar`.
- [ ] 5.2 Add a test for each new browser in the Literal (`chromium`, `brave`, `edge`, `safari`, `vivaldi`, `opera`, `opera_gx`) that asserts `read_cookies(source=...)` dispatches to the correct `browser_cookie3` function.
- [ ] 5.3 Add a test that `CookieAccessError` is raised (not propagated) when `browser_cookie3.chrome()` raises; confirm message contains no secret material and `__cause__` is set.
- [ ] 5.4 Add a test exercising the redaction path through the new adapter — `redact_cookie_for_event(cookie)` continues to strip `value` from LDD-bound events.
- [ ] 5.5 Confirm `tests/test_packages_independence.py` continues to pass — `cookie_store/store.py` SHALL NOT import `a2web.<domain>`.
- [ ] 5.6 Confirm contract tests under `tests/contracts/` pass without re-blessing — no wire-surface change.

## 6. Verification

- [ ] 6.1 Run `make check` (lint + ty + test-cov ≥85%). All green.
- [ ] 6.2 Run `make handler-probe` against Reddit + Discourse with `A2WEB_COOKIE_SOURCE=chrome` (the load-bearing real-cookie paths). Confirm no transport-layer regression.
- [ ] 6.3 Manually trigger the `cookies_refresh` MCP tool from Claude Code. Confirm the macOS Keychain prompt fires exactly once. Confirm subsequent fetches use the mirror without re-prompting.
- [ ] 6.4 Diff `cookies_refresh` response shape against the v0.8 baseline (RefreshResult fields). Confirm no breaking change.

## 7. Ship

- [ ] 7.1 Bump version in `pyproject.toml`.
- [ ] 7.2 Update `CHANGELOG.md` with: removed (~290 LoC of hand-rolled readers), added (browser-cookie3, pycryptodome transitively), unlocked (Chromium / Brave / Edge / Safari / Vivaldi / Opera / Opera GX; Linux + Windows for Chrome).
- [ ] 7.3 Run `make install-global` to refresh the global tool install + Claude Code MCP wiring.
- [ ] 7.4 Archive this change via the openspec workflow.
