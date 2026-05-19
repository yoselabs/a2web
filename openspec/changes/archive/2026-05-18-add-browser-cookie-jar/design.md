## Context

a2web today fetches with no cookie jar at all. The raw tier (curl_cffi) sends no cookies; the browser tier keeps per-host cookies warm in-memory but loses them when the BrowserContext is evicted. Meanwhile the same machine running a2web has a fully logged-in Chrome (or Firefox) profile sitting on disk. The gap matters for two distinct classes of URL: auth-gated content (NYT, FT, X/Twitter, Reddit NSFW, LinkedIn) and anti-bot-gated content where a real session cookie skips challenges.

This change introduces an opt-in cookie source that bridges that gap on macOS first. The user's main concern surfaced during exploration was supply-chain risk: any cookie-extraction library gets full access to every logged-in session on the machine. We audited `rookiepy` (YELLOW: dormant ~18 months, single maintainer, no PyPI Trusted Publishing) and `browser-cookie3` (even more dormant, LGPL-3.0). Both work; neither inspires confidence. Since the macOS Chrome path is genuinely small (~120 lines: sqlite read + `security` CLI + AES-GCM) we own it ourselves and remove the third-party trust dependency entirely.

The second non-trivial decision was the cookie-flow model. A read-through cache that hits the user's Chrome sqlite on every fetch would mean a macOS Keychain prompt per fetch and lock contention while Chrome is running. We chose a **mirror model** instead: an explicit `a2web cookies refresh` action reads Chrome → decrypts → upserts into a2web's own `SqliteResource`; fetches read from a2web's sqlite afterwards. Keychain prompt happens once per refresh; Chrome can stay running; staleness is observable as "last_refresh_at > N hours ago" rather than hidden behind a cache TTL.

The third decision worth recording is the agent-visibility channel for staleness. LDD events flow to operators (stderr, OTel), not into the tool response — agents never see them. `OperatorHint` is on `FetchResponse` and is the natural carrier; its existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) already serve both audiences in practice, despite an older docstring claiming "agents never read these." We update the docstring to match reality and use `code="cookies_stale"` for the new signal.

## Goals / Non-Goals

**Goals:**
- Opt-in browser cookie source (default off) for Chrome on macOS and Firefox on macOS.
- Single CLI/MCP action `a2web cookies refresh` is the only moment a Keychain prompt appears.
- Cookies thread through both raw (curl_cffi) and browser (Playwright) tiers automatically.
- Staleness is surfaced to the calling agent via `OperatorHint(code="cookies_stale", ...)` on every fetch when the mirror is older than the threshold (default 24h) or absent.
- Zero third-party cookie-extraction dependency. Only `cryptography` (already transitive via curl_cffi) is promoted to direct.
- Cookie values never appear in LDD events or structlog output.
- All Chrome-DB interaction goes through one isolatable function so tests can override the resource and never touch a real DB or Keychain.

**Non-Goals:**
- Linux/Windows Chrome (deferred — Chrome's app-bound encryption on Windows is a moving target; Linux keyring story is separate).
- Safari, Edge, Brave, Arc, Vivaldi, Opera (deferred — Firefox + Chrome is the bulk of real-world coverage).
- Multi-profile merge in a single refresh (settings selects one profile; running refresh again with a different profile name overwrites).
- LDD severity levels (separate a2kit feedback item; we emit at a single level today).
- Camoufox `user_data_dir=` inheritance (a different feature — would carry localStorage + storage state, not just cookies).
- Automatic background refresh / cron (the explicit-action model is the security contract — the user always knows when a Keychain prompt is about to appear).
- Write-back to the browser's cookie store (read-only).

## Decisions

### Mirror model over read-through cache

The mirror model has three concrete advantages that drove the choice over a per-fetch read of Chrome's sqlite:

1. **One Keychain prompt per refresh, not per fetch.** macOS pops a prompt the first time the `security` CLI accesses the "Chrome Safe Storage" item from a new binary; even with ACL pre-priming, hammering it per request is bad UX.
2. **No SQLite lock contention.** Chrome holds the cookie DB with shared locks; even with `cp` to a temp file, doing it per fetch adds latency. The mirror sidesteps it entirely.
3. **Staleness becomes observable.** `cookies_meta.last_refresh_at` is a single value the agent and operator can both reason about. A read-through cache hides freshness behind an opaque TTL.

The trade-off: refreshes can drift from the live browser state. Mitigated by surfacing staleness on every fetch when `cookie_source != "none"`.

### Hand-written reader vs `rookiepy` / `browser-cookie3`

Considered:
- **`rookiepy`** — broadest browser coverage, Rust binary, MIT license. **Rejected** after security audit: dormant ~18 months, single maintainer, no PyPI Trusted Publishing (long-lived token), unaddressed Chrome ABE issue. Code itself is clean (no network IO, no disk writes, no overreach) but the supply-chain posture is weak for a library handed all our cookies.
- **`browser-cookie3`** — pure Python, LGPL-3.0. **Rejected**: even more dormant (last release Jun 2023), LGPL adds compliance notes for downstream, same single-maintainer profile.
- **Hand-written** — selected. macOS Chrome reduces to: shell `security find-generic-password -wa "Chrome Safe Storage"` for the key, PBKDF2 with the known fixed salt ("saltysalt") and iteration count (1003 on macOS) to derive the AES key, AES-GCM (Chrome v11+) decrypt of `encrypted_value`. Firefox is plain SQLite read with no decryption. Total surface ~120 lines.

The `cryptography` library doing AES-GCM is itself a third party, but it's pyca/cryptography — Anthropic-tier maintenance, OpenSSF best-practices badge, OIDC-published — and it's already in our dep tree via curl_cffi. Promoting it to direct dep makes the dependency explicit rather than adding new trust surface.

### `OperatorHint` as the agent-visibility channel

Considered:
- Free-form append to `response.narrative` — works but unstructured; agent can't branch programmatically.
- New `response.meta["cookies_stale"] = "true"` — works but `meta` is currently informal `dict[str,str]`; agents would have to know the keys exist.
- New typed field `SessionState` on `FetchResponse` — strongest signal, but CLAUDE.md flags response envelope changes as breaking for parsers ("Ask First"). Defer until we need richer session info.
- Reuse `OperatorHint(code="cookies_stale", ...)` — selected. The `code` field is already used as a stable agent-readable branch point by `llm_unavailable`, `browser_unavailable`, `captcha_redirect`. The docstring says "agents never read these"; the docstring is descriptive of original intent, not technical reality. We update it.

### Storage in existing SqliteResource, two new tables

Considered a separate sqlite file in `~/.a2web/cookies.db`. **Rejected** — `SqliteResource` already exists as the "this-machine cache" lifecycle-managed resource. Adding tables there means we get lifecycle, journal mode, and lock handling for free; no new file path to surface in settings.

Schema:

```sql
CREATE TABLE IF NOT EXISTS a2web_cookies (
  profile     TEXT NOT NULL,
  browser     TEXT NOT NULL,    -- 'chrome' | 'firefox'
  host_key    TEXT NOT NULL,    -- Chrome-style: '.example.com' or 'example.com'
  name        TEXT NOT NULL,
  value       TEXT NOT NULL,    -- decrypted
  path        TEXT NOT NULL,
  expires_utc INTEGER,          -- unix seconds; NULL = session cookie
  is_secure   INTEGER NOT NULL, -- 0/1
  is_httponly INTEGER NOT NULL, -- 0/1
  samesite    TEXT,             -- 'lax' | 'strict' | 'none' | NULL
  PRIMARY KEY (profile, browser, host_key, name, path)
);

CREATE INDEX IF NOT EXISTS ix_a2web_cookies_host
  ON a2web_cookies (profile, browser, host_key);

CREATE TABLE IF NOT EXISTS cookies_meta (
  profile         TEXT NOT NULL,
  browser         TEXT NOT NULL,
  last_refresh_at INTEGER NOT NULL,  -- unix seconds
  refreshed_count INTEGER NOT NULL,
  PRIMARY KEY (profile, browser)
);
```

`refresh` is `DELETE WHERE profile/browser` + bulk `INSERT` inside one transaction, then `INSERT OR REPLACE` into `cookies_meta`. Atomic from the reader's perspective.

### Lazy-at-tool-seam, not on AppState

Per CLAUDE.md: heavy/conditional resources go through `app.provide(...)` and surface at the tool seam as `Lazy[T]`. `CookieJarResource` is conditional (only used when `cookie_source != "none"`) so it follows the same pattern as `BrowserPool` and `LlmExtractorResource`. **Not** on `AppState`. The fetch tool gains a `cookie_jar: Lazy[CookieJarResource]` kwarg; the new `cookies_refresh` tool likewise.

### Two tools, both via WebRouter

`fetch` already lives on `WebRouter`. The new `cookies_refresh` joins it there rather than creating a `CookiesRouter` — Typer's `web` group hosts both as `a2web web fetch` and `a2web web cookies refresh`. Actually, on reflection: the user said the CLI should be `a2web cookies refresh`, not `a2web web cookies refresh`. That implies a new top-level router `CookiesRouter(slug="cookies", tools=(refresh,))`. We take that route — small dedicated router, clean CLI verb grouping.

### Cookie domain matching

Chrome stores cookies with a `host_key` that's either `example.com` (host-only) or `.example.com` (domain match). On fetch we resolve cookies for `urlparse(url).netloc` by selecting:

- `host_key = host` (exact)
- `host_key = '.' || suffix` where suffix is a domain-suffix of host

Plus path matching (cookie's `path` must be a prefix of the URL path) and `is_secure` filtering (drop secure cookies when scheme is `http://`). The `expires_utc` check drops expired cookies — `NULL` means session cookie (kept; we behave like a long-lived session).

The Playwright shape conversion happens here too: `is_httponly` → `httpOnly`, `samesite` lowercase → titlecase enum.

### Cookie-value redaction

LDD payloads emit cookie *names*, *hosts*, and *counts* — never values. We add a small helper `redact(cookie) -> dict` used by every event emission. structlog uses the same helper. The mirror sqlite contains decrypted values (the entire point), so disk perms on the SqliteResource path are the security boundary there — already a user concern independent of this change.

### Test seam: override the resource, not the reader

`packages/cookie_store/chrome.py` is exercised only by manual testing on Denis's machine. CI never touches a real Chrome DB or Keychain. Tests use `client.override(CookieJarResource, FakeJar(rows))` to inject canned cookie rows. The fake implements the same `__aenter__` / `get_for_host` / `refresh` / `staleness_age` surface. The pure `packages/cookie_store/` module gets focused unit tests against canned sqlite fixtures (we can ship a test fixture sqlite with known plaintext, no encryption involved — the AES-GCM path is verified locally).

## Risks / Trade-offs

- **[Decrypted cookies on disk]** → SqliteResource path is user-controlled via settings; document the implication. The mirror is no more sensitive than the source Chrome DB it copies, and Chrome itself stores the same values plus an encryption envelope that any process running as the user can unwrap. Net surface: unchanged.
- **[Chrome encryption envelope changes]** → Chrome has changed encryption schemes before (v10 → v11, app-bound on Windows). The chrome.py reader is isolated — a future bump means editing one file. We accept the maintenance commitment in exchange for removing the third-party dependency.
- **[Stale cookies cause silent auth failures]** → mitigated by the staleness `OperatorHint` on every fetch. The agent can branch on `code == "cookies_stale"` and run `cookies_refresh` itself, or surface the hint to the user.
- **[Keychain prompt UX]** → unavoidable on first refresh from a new binary. macOS's `security` CLI honors per-user ACL persistence; subsequent prompts are typically suppressed. We don't try to suppress the first prompt — it's a security feature, not a bug.
- **[Cookies sent to wrong tier]** → Jina tier is a remote reader (`r.jina.ai`); sending the user's cookies through it would leak the session to a third party. We explicitly skip Jina in the cookie wiring — only raw + browser tiers receive cookies.
- **[Cookie injection across hosts]** → domain matching must be exact: `evil.example.com`'s cookies must not flow to `example.com`. The matching logic is small but security-relevant; we cover host-only, domain-match, secure-flag, and path-prefix in tests.
- **[Lock contention with running Chrome during refresh]** → `cp` to tempdir before reading. macOS APFS makes this O(1). Worst case Chrome is mid-write and we get a slightly-stale snapshot; on the next refresh we get the newer state. Not a correctness issue.

## Open Questions

None blocking. Two future considerations worth noting (not in scope here):

- Whether to grow the `SessionState` typed field on `FetchResponse` if more session signals accumulate (currently just cookies; future could include CF clearance state, custom auth headers, etc).
- Whether the v2 `cookies_refresh` should support `--all-profiles` and merge — depends on whether real usage hits the limitation.
