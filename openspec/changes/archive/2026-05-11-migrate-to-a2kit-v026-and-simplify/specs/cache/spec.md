## REMOVED Requirements

### Requirement: Cache schema

**Reason:** Replaced by hishel's `SQLiteStorage`. Hishel owns the schema; a2web owns the curl_cffi response shim that adapts our HTTP responses to hishel's sans-I/O Controller.

**Migration:** Delete the hand-rolled `cache` table schema in `src/a2web/cache/sqlite_cache.py`. Existing `~/.a2web/cache.sqlite` files from v0.1.0 are abandoned at upgrade time; users get a fresh cache. CHANGELOG documents the break.

### Requirement: Profile hash isolates cached bodies

**Reason:** Hishel handles cache invalidation via HTTP cache directives + storage-level keying. Custom `profile_hash` over settings fields is redundant — the few settings that genuinely affect upstream behavior (`default_ua`, `stealth`) translate to request headers that hishel's vary-header support already considers.

**Migration:** Delete `compute_profile_hash` from `src/a2web/cache/sqlite_cache.py`. Settings that should affect cache keys SHALL be reflected in request headers (User-Agent, Accept-*), which hishel includes in its key derivation when those headers appear in upstream `Vary` responses.

## MODIFIED Requirements

### Requirement: Cache hit, miss, and bypass paths

The system SHALL adapt curl_cffi responses to hishel's sans-I/O `Controller` via a shim in `src/a2web/cache/__init__.py`. The shim SHALL:

- Translate curl_cffi `Response` to httpcore-compatible request/response objects (≤ 80 LOC target; if exceeded, hishel adoption is deferred per design D5).
- Call `controller.handle_request(...)` to determine `FromCache` / `NeedRevalidation` / `NeedToBeUpdated`.
- For `FromCache`: return the cached body without any network call; orchestrator emits `FetchResponse.cache == "hit"`.
- For `NeedRevalidation`: issue a conditional GET via the resolved tier; on 304 reuse cached body and orchestrator emits `cache == "hit"`.
- For `NeedToBeUpdated`: cache the new response via `controller.handle_response(...)`; orchestrator emits `cache == "miss"`.

Hosts in `state.settings.live_only_hosts` SHALL bypass the cache entirely (no read, no write); orchestrator emits `cache == "bypass"`.

#### Scenario: Cache hit returns cached body

- **WHEN** hishel determines `FromCache` for a URL with a fresh entry
- **THEN** the shim returns the cached body and the orchestrator emits `FetchResponse.cache == CacheState.hit` with no upstream HTTP request

#### Scenario: 304 conditional hit

- **WHEN** hishel determines `NeedRevalidation` and the conditional GET returns 304
- **THEN** the shim returns the cached body, the response is recorded as `cache == CacheState.hit`, and no body bytes are transferred from upstream

#### Scenario: Live-only host bypasses

- **WHEN** the URL host is in `state.settings.live_only_hosts`
- **THEN** the cache shim is not invoked; orchestrator emits `cache == CacheState.bypass`

### Requirement: Block pages never cached

The orchestrator SHALL pass the response to hishel's `controller.handle_response(...)` ONLY when the gate verdict is `Verdict.ok`. Any non-OK verdict SHALL skip the cache write path. This invariant SHALL be tested directly.

#### Scenario: Block page is not handed to hishel

- **WHEN** the orchestrator processes a response that triggers any block-page regex (gate verdict ≠ ok)
- **THEN** `controller.handle_response(...)` is not called, and inspecting hishel's storage shows no entry for the URL

#### Scenario: Length-floor failure is not handed to hishel

- **WHEN** the orchestrator emits `Verdict.length_floor`
- **THEN** the cache write path is skipped

## ADDED Requirements

### Requirement: aiosqlite removed if no longer reachable

After hishel adoption, the system SHALL audit `src/a2web/` for any remaining import of `aiosqlite`. If no module reaches it, the `aiosqlite` dependency SHALL be removed from `pyproject.toml` in the same change that lands hishel.

#### Scenario: aiosqlite drop verified

- **WHEN** `make check` runs after Phase B completes
- **THEN** `grep -r "import aiosqlite" src/` produces no matches AND `pyproject.toml` does not list `aiosqlite` as a dependency

### Requirement: hishel as a top-level dependency

`pyproject.toml` SHALL declare `hishel>=0.1,<2` (or the current major series at adoption time) as a top-level runtime dependency. The shim module SHALL import hishel symbols from documented public API surface only.

#### Scenario: hishel installable in fresh environment

- **WHEN** `uv sync --all-extras` runs against a clean environment
- **THEN** `hishel` is installed AND `from hishel import Controller, SQLiteStorage` succeeds
