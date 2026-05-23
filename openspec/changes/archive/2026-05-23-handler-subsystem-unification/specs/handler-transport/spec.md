## ADDED Requirements

### Requirement: Shared fetch primitive provides curl_cffi-impersonated transport

The system SHALL provide an `async` callable in `packages/http_fetch` — `fetch_bytes(url, *, headers, timeout_s, proxy_url=None, cookies=None, conditional_extras=None, breaker=None) -> FetchOutcome` — that performs every HTTP fetch on behalf of `RawTier`, `ArchiveTier`, and every site handler. The primitive SHALL dispatch requests via `curl_cffi.AsyncSession` with Chrome JA3/JA4 TLS impersonation. The primitive SHALL NOT raise on routine HTTP failures; it SHALL map them to closed `Verdict` values on the returned `FetchOutcome` (`ok`, `not_found`, `rate_limited`, `connection_error`, `timeout`, `proxy_unavailable`, `content_type_mismatch`).

#### Scenario: Chrome TLS impersonation is the default

- **WHEN** any caller invokes `fetch_bytes(url, ...)`
- **THEN** the underlying `curl_cffi.AsyncSession` is constructed with `impersonate=` set to the project's current Chrome default

#### Scenario: Routine HTTP failures yield a verdict, not an exception

- **WHEN** the upstream returns 404 / 429 / 5xx, times out, or the underlying client raises a connection error
- **THEN** `fetch_bytes` returns a `FetchOutcome` with the corresponding closed `Verdict` (`not_found`, `rate_limited`, `connection_error`, `timeout`) and never propagates the underlying exception

### Requirement: Primitive integrates proxy routing

`fetch_bytes` SHALL accept an optional `proxy_url`. When set, the underlying request SHALL be dispatched through that proxy. A proxy-side failure (proxy connection refused, proxy 502, proxy timeout) SHALL surface as `Verdict.proxy_unavailable` on the returned `FetchOutcome`. The primitive SHALL NOT silently retry direct on proxy failure.

#### Scenario: proxy_url is plumbed to the underlying client

- **WHEN** `fetch_bytes(url, proxy_url="socks5://localhost:1080", ...)` is called
- **THEN** the underlying request carries `proxies={"http": "socks5://localhost:1080", "https": "socks5://localhost:1080"}`

#### Scenario: Proxy failure returns proxy_unavailable, no direct retry

- **WHEN** the configured proxy is unreachable and the underlying client raises a proxy error
- **THEN** the returned `FetchOutcome.verdict == Verdict.proxy_unavailable` and no direct (un-proxied) request is issued

### Requirement: Primitive integrates per-host circuit breakers

`fetch_bytes` SHALL accept an optional `breaker` handle. When provided, the fetch SHALL run within the breaker's context manager; a breaker-open state SHALL short-circuit the call with a closed-verdict `FetchOutcome` without issuing an outbound request.

#### Scenario: Breaker open short-circuits the fetch

- **WHEN** the supplied breaker is in the open state for the host
- **THEN** `fetch_bytes` returns a closed-verdict `FetchOutcome` and no network request is issued

### Requirement: Primitive forwards cookies and conditional-GET extras

`fetch_bytes` SHALL accept `cookies: dict[str, str] | None` and forward them to the underlying request when non-empty. It SHALL accept `conditional_extras: dict[str, str] | None` and translate `etag` / `last_modified` keys into `If-None-Match` / `If-Modified-Since` request headers. A 304 response SHALL surface as `FetchOutcome.conditional_hit == True` with `Verdict.ok` and an empty body (the orchestrator reuses the cached body).

#### Scenario: Cookies forwarded

- **WHEN** `fetch_bytes(url, cookies={"sid": "x"})` is called
- **THEN** the outbound request includes the `sid=x` cookie

#### Scenario: Conditional extras drive 304 handling

- **WHEN** `fetch_bytes(url, conditional_extras={"etag": "W/abc"})` is called and the upstream returns 304
- **THEN** the returned `FetchOutcome` has `verdict == Verdict.ok`, `conditional_hit == True`, and empty body

### Requirement: Primitive does not log cookie or auth values

The primitive SHALL NOT log cookie values, `Authorization` header values, or any other credential material. Diagnostic-friendly output MAY indicate that cookies / auth were attached (count, header name) but SHALL NOT contain any secret value.

#### Scenario: Diagnostic redacts cookie value

- **WHEN** `fetch_bytes(url, cookies={"sid": "supersecret"})` is called and any diagnostic / log entry is emitted by the primitive
- **THEN** the entry contains no substring `"supersecret"`
