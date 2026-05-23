## MODIFIED Requirements

### Requirement: RawTier uses curl_cffi with TLS impersonation

The system SHALL implement `RawTier` in `src/a2web/tiers/raw.py` via the shared `handler-transport` primitive (`packages/http_fetch.fetch_bytes`), which uses `curl_cffi` with Chrome JA3/JA4 impersonation (`impersonate="chrome120"` or the project's current default). The default user-agent SHALL come from `state.settings.default_ua`. The default request timeout SHALL be 10 seconds (overridable per call). `RawTier` SHALL NOT construct `curl_cffi.AsyncSession` directly; the primitive owns the session lifecycle and impersonation choice.

#### Scenario: Tier name is `raw`

- **WHEN** `RawTier()` is instantiated
- **THEN** `tier.name == "raw"`

#### Scenario: TLS impersonation enabled

- **WHEN** the tier issues a request
- **THEN** the underlying call (via `fetch_bytes`) uses `impersonate=` and the request is dispatched with the Chrome TLS fingerprint

#### Scenario: User-agent comes from settings

- **WHEN** the tier issues a request with `state.settings.default_ua = "MyAgent/1.0"`
- **THEN** the outbound `User-Agent` header is `"MyAgent/1.0"`

#### Scenario: RawTier does not construct curl_cffi sessions directly

- **WHEN** `tiers/raw.py` is inspected
- **THEN** it imports neither `curl_cffi.requests.AsyncSession` nor any equivalent session constructor; every outbound request runs through `fetch_bytes`
