## ADDED Requirements

### Requirement: Cache schema

The system SHALL define a single sqlite table `cache` in `src/a2web/cache/sqlite_cache.py` with columns `(url, profile_hash, etag, last_modified, fetched_at, expires_at, status_code, content_type, content_hash, body)`. PRIMARY KEY is `(url, profile_hash)`. `body` SHALL be gzip-compressed. A secondary index on `content_hash` SHALL exist for dedup queries.

#### Scenario: Schema exists after sqlite open

- **WHEN** `_open_sqlite_with_schema(settings)` is called against a fresh database
- **THEN** the `cache` table exists with the documented columns and the `cache_content_hash` index is present

### Requirement: Profile hash isolates cached bodies

The system SHALL compute `profile_hash` as a stable hash of the settings fields that affect the upstream request shape (`default_ua`, `stealth`, eventually proxy id). Different profiles SHALL produce different cache keys for the same URL.

#### Scenario: UA change yields different cache row

- **WHEN** the same URL is cached under settings A (`default_ua="UA-A"`) and settings B (`default_ua="UA-B"`)
- **THEN** two distinct rows exist in the `cache` table

### Requirement: Cache hit, miss, and bypass paths

The system SHALL expose async functions `cache_get(conn, url, profile_hash) -> CacheRow | None` and `cache_put(conn, url, profile_hash, row) -> None`. Hosts in `state.settings.live_only_hosts` SHALL bypass the cache (no read, no write).

#### Scenario: Cache hit returns the row

- **WHEN** an entry exists and `expires_at > now`
- **THEN** `cache_get` returns the row and the orchestrator emits `FetchResponse.cache == "hit"`

#### Scenario: Cache miss returns None

- **WHEN** no entry exists
- **THEN** `cache_get` returns `None` and the orchestrator emits `FetchResponse.cache == "miss"`

#### Scenario: Live-only host bypasses cache

- **WHEN** the URL host is in `state.settings.live_only_hosts`
- **THEN** `cache_get` returns `None`, `cache_put` is a no-op, and the orchestrator emits `FetchResponse.cache == "bypass"`

### Requirement: Block pages never cached

The system SHALL NOT write to the cache when the gate verdict is anything other than `Verdict.ok`. This invariant SHALL be tested directly.

#### Scenario: Length-floor failure is not written

- **WHEN** extraction returns `<500` chars and the gate emits `Verdict.length_floor`
- **THEN** the row count in `cache` is unchanged after the fetch
