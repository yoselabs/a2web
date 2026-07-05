# raw-tier Specification

## Purpose
TBD - created by archiving change pr3-raw-tier. Update Purpose after archive.
## Requirements
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

### Requirement: HTTP failures map to closed-enum verdicts

The system SHALL map curl_cffi exceptions and HTTP status codes to the closed `Verdict` enum:

- Connection refused / DNS / TLS handshake errors → `Verdict.connection_error`
- Timeout → `Verdict.timeout`
- 404 → `Verdict.not_found`
- 429 → `Verdict.rate_limited`
- 5xx → `Verdict.connection_error`
- 2xx with a JSON content-type (`application/json`, `application/<x>+json`, `text/json`) → `Verdict.ok` (a JSON response is first-class content, not a mismatch — it is synthesized to markdown downstream, never escalated to the jina HTML reader)
- 2xx with a non-HTML, non-JSON content type when HTML expected → `Verdict.content_type_mismatch`
- 2xx HTML otherwise → `Verdict.ok`

The JSON carve-out SHALL be evaluated BEFORE the non-HTML mismatch check, so a JSON response never maps to `content_type_mismatch`. Detection SHALL use a shared `_is_json_content_type` predicate (also consulted by the extract phase) so the raw tier and the orchestrator agree on what counts as JSON.

#### Scenario: 404 maps to not_found

- **WHEN** the tier receives an HTTP 404 response
- **THEN** the returned `TierResult.verdict == Verdict.not_found` and `status_code == 404`

#### Scenario: Timeout does not raise

- **WHEN** the upstream host fails to respond within the timeout
- **THEN** the tier returns a `TierResult` with `verdict == Verdict.timeout`, NOT a raised `TimeoutError` propagating through the orchestrator

#### Scenario: 2xx JSON response maps to ok

- **WHEN** the tier receives an HTTP 200 with `content-type: application/json`
- **THEN** `TierResult.verdict == Verdict.ok` and `TierResult.content_type` carries the JSON content-type through to extraction

#### Scenario: 2xx JSON-family content-type maps to ok

- **WHEN** the tier receives an HTTP 200 with `content-type: application/vnd.api+json` (a `+json` suffix type)
- **THEN** `TierResult.verdict == Verdict.ok`

#### Scenario: 2xx non-JSON non-HTML still mismatches

- **WHEN** the tier receives an HTTP 200 with `content-type: application/pdf`
- **THEN** `TierResult.verdict == Verdict.content_type_mismatch` (unchanged — only JSON is carved out)

### Requirement: Conditional GET on cache hit

The system SHALL, when a cached entry exists for `(url, profile_hash)`, send `If-None-Match` (from cached `etag`) and/or `If-Modified-Since` (from cached `last_modified`) with the request. A 304 response SHALL produce `TierResult.verdict == Verdict.ok` with `body` populated from cache and `tier_extras["conditional_hit"] == True`.

#### Scenario: 304 response reuses cached body

- **WHEN** the cache holds an entry with `etag="W/abc"` for a URL and the upstream returns 304
- **THEN** the orchestrator emits `FetchResponse.cache == "hit"` and the response body is the cached body

### Requirement: Raw tier accepts proxy_url and surfaces proxy_unavailable

`RawTier.fetch` SHALL accept an optional `proxy_url: str | None = None` keyword. When set, it SHALL be passed to `curl_cffi.requests.get` via `proxies={"http": proxy_url, "https": proxy_url}`. When unset, the call SHALL be made directly (current behavior unchanged).

When the proxy layer fails (proxy connection refused, proxy 502, proxy timeout), the tier SHALL return `Verdict.proxy_unavailable` with `tier_extras["proxy_url"]` populated for diagnostics. The tier SHALL NOT silently retry direct.

#### Scenario: Direct fetch unchanged

- **WHEN** `RawTier.fetch` is called with `proxy_url=None`
- **THEN** the resulting `curl_cffi` request carries no `proxies` argument and behavior matches PR3

#### Scenario: Proxy URL plumbed to curl_cffi

- **WHEN** `RawTier.fetch` is called with `proxy_url="socks5://localhost:1080"`
- **THEN** the captured `curl_cffi.requests.get` call has `proxies == {"http": "socks5://localhost:1080", "https": "socks5://localhost:1080"}`

#### Scenario: Proxy refused yields proxy_unavailable verdict

- **WHEN** the proxy is unreachable and `curl_cffi` raises a proxy connection error
- **THEN** the tier returns `verdict == Verdict.proxy_unavailable` and does NOT issue a direct request

### Requirement: Raw tier accepts and forwards a per-fetch cookies dict

`RawTier.fetch` SHALL accept an optional `cookies: dict[str, str] | None = None` keyword. When set and non-empty, the value SHALL be passed through to `curl_cffi.requests.get` as its `cookies=` argument. When unset or empty, no `cookies=` argument SHALL be passed (current behavior unchanged).

The raw tier SHALL NOT log cookie values. Diagnostic rows for the raw step MAY indicate that cookies were attached (count + first name) but SHALL NOT contain any cookie value.

#### Scenario: No cookies argument when None

- **WHEN** `RawTier.fetch(url, cookies=None)` is called
- **THEN** the captured `curl_cffi.requests.get` call does not pass a `cookies=` kwarg

#### Scenario: No cookies argument when empty dict

- **WHEN** `RawTier.fetch(url, cookies={})` is called
- **THEN** the captured `curl_cffi.requests.get` call does not pass a `cookies=` kwarg

#### Scenario: Cookies dict is forwarded

- **WHEN** `RawTier.fetch(url, cookies={"sid": "x"})` is called
- **THEN** the captured `curl_cffi.requests.get` call has `cookies == {"sid": "x"}`

#### Scenario: Diagnostic redacts cookie value

- **WHEN** the raw tier emits a diagnostic for a fetch with `cookies={"sid": "supersecret"}`
- **THEN** the rendered diagnostic row contains no substring `"supersecret"`

### Requirement: JSON body served under a non-JSON content-type is recovered

The raw tier SHALL sniff a 2xx response body whose content-type is not JSON-family: if the body parses as a JSON document, the tier SHALL normalize the returned `TierResult.content_type` to `application/json` and set `Verdict.ok`, so the orchestrator synthesizes it in-place (json-endpoint-direct-routing) instead of running trafilatura over JSON or escalating to the jina HTML reader (both of which mangle it into a false `length_floor`).

The sniff SHALL be prefix-guarded — only a body opening with `{` or `[` (checked within a bounded leading window, never a full-body `lstrip`) is decoded and parsed — so large HTML/binary bodies are never decoded. Because real HTML never parses as a JSON document, the sniff SHALL only ever upgrade a genuine JSON body; a non-JSON body is left untouched.

The parse SHALL go through the `json_in_script` package's `sniff_json_body`, keeping the json-loads-funnel invariant intact (no new `json.loads` in the tier).

#### Scenario: JSON served as text/html is normalized to application/json

- **WHEN** the raw tier receives an HTTP 200 with `content-type: text/html` but a body that parses as JSON (e.g. `{"items": [{"title": "A"}]}`)
- **THEN** the returned `TierResult.verdict == Verdict.ok` and `TierResult.content_type == "application/json"`

#### Scenario: JSON served as text/plain is normalized

- **WHEN** the raw tier receives an HTTP 200 with `content-type: text/plain` and a JSON body
- **THEN** `TierResult.content_type` is normalized to `application/json` (verdict `ok`), not left as a `content_type_mismatch`

#### Scenario: A genuine HTML page is not mis-sniffed

- **WHEN** the raw tier receives an HTTP 200 `text/html` page with an HTML body (`<html>…`)
- **THEN** `TierResult.content_type` stays `text/html` and the body is not treated as JSON

#### Scenario: A binary body is never decoded

- **WHEN** the raw tier receives a body opening with non-`{`/`[` bytes (e.g. a PDF `%PDF-…`)
- **THEN** the sniff short-circuits on the prefix guard without decoding or parsing the body

