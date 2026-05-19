## ADDED Requirements

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
