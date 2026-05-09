## ADDED Requirements

### Requirement: RawTier uses curl_cffi with TLS impersonation

The system SHALL implement `RawTier` in `src/a2web/tiers/raw.py` using `curl_cffi` with Chrome JA3/JA4 impersonation (`impersonate="chrome120"` or current default). The default user-agent SHALL come from `state.settings.default_ua`. The default request timeout SHALL be 10 seconds (overridable per call later).

#### Scenario: Tier name is `raw`

- **WHEN** `RawTier()` is instantiated
- **THEN** `tier.name == "raw"`

#### Scenario: TLS impersonation enabled

- **WHEN** the tier issues a request
- **THEN** the underlying `curl_cffi` call uses `impersonate=` and the request is dispatched with the Chrome TLS fingerprint

#### Scenario: User-agent comes from settings

- **WHEN** the tier issues a request with `state.settings.default_ua = "MyAgent/1.0"`
- **THEN** the outbound `User-Agent` header is `"MyAgent/1.0"`

### Requirement: HTTP failures map to closed-enum verdicts

The system SHALL map curl_cffi exceptions and HTTP status codes to the closed `Verdict` enum:

- Connection refused / DNS / TLS handshake errors → `Verdict.connection_error`
- Timeout → `Verdict.timeout`
- 404 → `Verdict.not_found`
- 429 → `Verdict.rate_limited`
- 5xx → `Verdict.connection_error` (PR7 will refine)
- 2xx with non-HTML content type when HTML expected → `Verdict.content_type_mismatch`
- 2xx HTML otherwise → `Verdict.ok`

#### Scenario: 404 maps to not_found

- **WHEN** the tier receives an HTTP 404 response
- **THEN** the returned `TierResult.verdict == Verdict.not_found` and `status_code == 404`

#### Scenario: Timeout does not raise

- **WHEN** the upstream host fails to respond within the timeout
- **THEN** the tier returns a `TierResult` with `verdict == Verdict.timeout`, NOT a raised `TimeoutError` propagating through the orchestrator

### Requirement: Conditional GET on cache hit

The system SHALL, when a cached entry exists for `(url, profile_hash)`, send `If-None-Match` (from cached `etag`) and/or `If-Modified-Since` (from cached `last_modified`) with the request. A 304 response SHALL produce `TierResult.verdict == Verdict.ok` with `body` populated from cache and `tier_extras["conditional_hit"] == True`.

#### Scenario: 304 response reuses cached body

- **WHEN** the cache holds an entry with `etag="W/abc"` for a URL and the upstream returns 304
- **THEN** the orchestrator emits `FetchResponse.cache == "hit"` and the response body is the cached body
