## ADDED Requirements

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
