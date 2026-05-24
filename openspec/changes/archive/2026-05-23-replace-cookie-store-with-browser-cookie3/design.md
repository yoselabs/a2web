## Context

The `cookie_store` package was built in a2web v0.8 to mirror a single browser profile into our SqliteResource so authenticated fetches can succeed on sites that gate behind login (Reddit, X, Discourse). Two readers exist today: `chrome.py` (macOS-only, uses the `security` CLI to pull the Chrome Safe Storage key from the Keychain, then decrypts the `Cookies` sqlite via AES-128-CBC using `cryptography`), and `firefox.py` (cross-platform, raw read of `cookies.sqlite`).

The Chrome reader is the load-bearing piece — it's also the one most likely to rot: Chrome v20 introduced macOS Keychain ACL gating and Windows uses DPAPI; Linux uses gnome-keyring / KWallet with AES-CBC-128 against a fallback key. Every browser variant (Brave, Edge, Vivaldi, Opera) ships its own Keychain entry name. The cost of keeping `chrome.py` correct across the OS × browser-variant matrix is unbounded.

`browser-cookie3` is a single-mission Python library (8+ years, dominant ecosystem position — yt-dlp, instaloader, snscrape) whose entire purpose is to extract cookies from any local browser on any OS. It handles every cell of that matrix.

D6 of the 2026-05-22 generic-record-extraction proposal rejected outsourcing JSON-LD parsing to extruct because the mission overlap was small. The mission overlap with `browser-cookie3` is total: read browser cookies → return cookies. This is the case where outsourcing is unambiguously correct.

## Goals / Non-Goals

**Goals:**
- Shrink `cookie_store` from ~375 LoC of OS-specific decryption to a thin adapter (≤100 LoC) that converts `browser-cookie3`'s `http.cookiejar.CookieJar` output to our existing `Cookie` boundary dataclass.
- Unlock Chrome / Chromium / Brave / Edge / Vivaldi / Opera / Opera GX / Safari on macOS, Linux, and Windows without further code.
- Preserve every observable behavior of v0.8: `cookies_refresh` is still the only Keychain-prompt moment, `cookies_stale` `OperatorHint` still surfaces on every fetch past TTL, `CookiesStale` LDD event still fires, cookie values are still redacted in LDD events and structlog.
- Preserve the `packages/` independence invariant — `cookie_store` continues to have zero `a2web.<domain>` imports.

**Non-Goals:**
- No change to the `a2web_cookies` / `cookies_meta` SQLite schema. Existing user data continues to work.
- No change to the `CookiesRouter` MCP wire surface — `cookies_refresh` tool args and response shape are frozen.
- No change to the `CookieJarResource` provider registration in `server.py`. The `app.provide(build_cookie_jar)` line is untouched.
- No change to the async chokepoint pattern. `browser-cookie3` is sync; we keep the existing `asyncio.to_thread` wrapper.
- No new browser support beyond what `browser-cookie3` provides today. We do not implement custom Safari / Brave readers.
- No fallback "if browser-cookie3 fails, use our old reader" mode. The library either works or we surface the error through the existing `OperatorHint` path.

## Decisions

### D1 — Adopt `browser-cookie3` as the sole cookie source

**Decision**: Delete `chrome.py` and `firefox.py`. Replace with `store.py` (single file, ~80 LoC) that calls `browser_cookie3.<browser>(domain_name=None, cookie_file=None)` based on `settings.cookie_source` and adapts the returned `http.cookiejar.CookieJar` into a `list[Cookie]` using our existing `Cookie` dataclass.

**Why**: Mission match is total. The library has 8+ years of maintenance momentum, dominant ecosystem position, and handles every OS × browser cell we care about plus several we don't. Hand-rolling the same matrix is unbounded work for no architectural gain.

**Alternatives considered**:
- *Keep Chrome reader, adopt browser-cookie3 only for new browsers*: doubles the test surface, retains the rot risk on Chrome (the most-used path).
- *Fork browser-cookie3*: rejected. We have no requirements the upstream doesn't already meet; forking creates a maintenance liability with zero offsetting benefit.
- *Wait for `cryptography` to add a browser-cookie reader*: it won't. `cryptography` is intentionally low-level.

### D2 — Widen `cookie_source` Literal to the full browser-cookie3 set

**Decision**: `cookie_source: Literal["none", "chrome", "chromium", "brave", "edge", "firefox", "safari", "vivaldi", "opera", "opera_gx"]` (default `"none"`).

**Why**: One env var per browser is the obvious surface. Users on Brave today must lie and claim `chrome`; this fixes that.

**Alternatives considered**:
- *Keep `chrome | firefox` and detect family internally*: rejected — strips user control. If the user has both Chrome and Brave installed we cannot guess intent.
- *Free-form string passed to `browser_cookie3`*: rejected — typo-prone, no schema validation, breaks AppSettings introspection.

### D3 — Accept `pycryptodome` as a transitive dep

**Decision**: Do not pin or replace `pycryptodome`. It enters via `browser-cookie3`'s requirements.

**Why**: We already have `cryptography` (used by curl_cffi). Adding `pycryptodome` is a deliberate, scoped cost — ~5MB, no symbol conflict (different namespace: `Crypto.*` vs `cryptography.*`), no transitive bloat. The alternative is patching `browser-cookie3` to use `cryptography` — out of scope and politically fragile.

**Alternatives considered**:
- *Vendor browser-cookie3 with cryptography swap*: rejected — see D1 alt.
- *Pin pycryptodome ourselves to control transitive resolution*: rejected — premature. Pin only if a conflict appears.

### D4 — Adapter lives at `packages/cookie_store/store.py`, single file

**Decision**: Single adapter file, not a `chrome.py` / `firefox.py` / `safari.py` split.

**Why**: The pre-`browser-cookie3` split existed because each reader was 100-200 LoC of distinct logic. After the swap, every reader is a one-liner (`return browser_cookie3.<name>(cookie_file=...)`). A per-browser file would be ceremony.

**Alternatives considered**:
- *Per-browser file with a dispatch shim*: rejected — premature structure.
- *Inline into `__init__.py`*: rejected — keeps `__init__.py` for re-exports only, matches the rest of `packages/`.

### D5 — Preserve v0.8 "Keychain prompt only on cookies_refresh" UX

**Decision**: `CookieJarResource.__aenter__` does NOT call browser-cookie3. Only `cookies_refresh` does. The mirrored cookies in `a2web_cookies` are the read path for normal fetches.

**Why**: `browser_cookie3.chrome()` triggers the Keychain ACL prompt on macOS. Calling it during resource init would fire that prompt on every server cold start — terrible UX. The existing v0.8 design (refresh is a user-initiated tool call; fetches read from the mirror) already solves this; we just keep it.

**Alternatives considered**:
- *Lazy-init on first fetch*: rejected — same prompt-on-start-of-work problem in a slightly different shape.
- *Polling refresh in background*: rejected — wakes the Keychain prompt at unpredictable times.

### D6 — No behavioral compatibility shim for the deleted reader internals

**Decision**: Delete `chrome.py` / `firefox.py` outright. Do not keep them as `_legacy_*.py` fallbacks.

**Why**: The packages/ independence rule and CLAUDE.md "no backwards-compat shims for removed code" both push toward a clean cut. The behavior we promise is observable (cookies appear in `a2web_cookies`, `cookies_refresh` returns counts, `cookies_stale` hint fires past TTL); the mechanism is not promised by any spec.

## Risks / Trade-offs

- **[browser-cookie3 single-maintainer bus factor]** → *Mitigation*: library has 8+ years of momentum and the fork landscape is healthy (yt-dlp's vendor copy is the canonical alternative). If upstream dies, vendoring is a known-cost escape hatch (~1KLoC, mostly stable code).
- **[pycryptodome import surface enters the project]** → *Mitigation*: we don't import it from a2web code, only browser-cookie3 does. If a future security advisory requires patching, `uv` lockfile handling is the standard knob. `cryptography` and `pycryptodome` have coexisted in major projects (e.g., scrapy + paramiko stacks) for years.
- **[browser-cookie3 may not match our current `Cookie` boundary-field semantics exactly]** → *Mitigation*: the adapter is the single point of conversion. If an edge case appears (e.g., `expires=0` semantics, sameSite encoding), it's fixed in one place.
- **[Keychain prompt timing regresses unintentionally]** → *Mitigation*: D5 keeps the v0.8 contract explicit. The CookieJarResource's `_ensure()` MUST NOT call into browser-cookie3 — only the `cookies_refresh` code path does. The spec scenario "Keychain prompt only fires on cookies_refresh" tests this.
- **[Linux / Windows behavior is now claimed but untested in CI]** → *Mitigation*: tag the new platform scenarios `@platform-linux` / `@platform-windows` and leave them as live-network probes (like `handler-probe`) rather than CI assertions. CI continues to run macOS-only. The promise is "browser-cookie3 supports it" not "we test it".
- **[Mirror staleness window may surprise users on new browsers]** → *Mitigation*: no change. The `cookies_stale` `OperatorHint` and `cookie_stale_after_hours` setting already cover this signal.

## Migration Plan

1. Add `browser-cookie3` to `pyproject.toml`; `uv lock` to bring in pycryptodome transitively.
2. Land `packages/cookie_store/store.py` (new) with the adapter. Existing `chrome.py` / `firefox.py` stay in place during the diff.
3. Switch the `cookie_store/__init__.py` re-exports to point at `store.py`.
4. Update `cookie_jar.py` (domain glue) call sites to use the new adapter API.
5. Update `AppSettings.cookie_source` Literal to the widened set.
6. Rewrite `tests/test_packages_cookie_store_chrome.py` / `_firefox.py` as `tests/test_packages_cookie_store.py` against the new adapter (using monkeypatched `browser_cookie3.<name>` fakes).
7. Delete `chrome.py` and `firefox.py`.
8. Run `make check` (lint + ty + test-cov ≥85%).
9. Run `make handler-probe` to confirm no transport-layer regression in the cookie-affected handlers (Reddit, Discourse).
10. Bump version, `make install-global` to refresh the Claude-Code-side MCP install.

**Rollback**: a single revert restores the deleted readers — they're self-contained and stay in git history. `browser-cookie3` and `pycryptodome` can stay in the dep tree (inert) until a follow-up cleanup; or a force-add reverts pyproject.toml too.

## Open Questions

- Should `cookie_source` accept comma-separated values (e.g., `chrome,brave`) to mirror cookies from multiple browsers into one jar? *Defer*: not a v0.8 capability, no demand signal yet. Add later if a user asks.
- Should we add a `cookies_refresh --browser=brave` override that ignores `settings.cookie_source` for one-off mirroring? *Defer*: ask after first multi-browser user surfaces.
- Does browser-cookie3 honor `cookie_profile != "Default"` consistently across all browsers? *Investigate during implementation*: the library accepts a `cookie_file=` override but profile-name → file-path mapping varies per browser. Document the resolved mapping in `cookie_store/__init__.py` docstring.
