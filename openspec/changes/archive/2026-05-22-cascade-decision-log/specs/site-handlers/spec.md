## ADDED Requirements

### Requirement: no_match is reserved for URLs no handler claims

A result dispatched through `SiteHandlerTier` SHALL set `no_match` (or `skipped`) on its `TierResult` ONLY to mean "no registered handler claims this URL." A handler that DOES claim a URL — its `matches(url)` returned `True` — but fails to retrieve usable content SHALL return a real closed-enum `Verdict` observation, never `no_match`. This covers, in particular: an upstream soft-block (an HTTP 200 carrying a throttle or error body, e.g. Reddit's `{"error": 429}`), an empty listing, and a deleted or removed thread. A matched-but-failed handler result SHALL produce an observation / diagnostic row in the cascade log; only a genuine no-handler-claims outcome is silently skipped.

#### Scenario: Reddit soft-block surfaces as a real verdict

- **WHEN** the Reddit handler claims a listing URL and the `.json` endpoint returns HTTP 200 with a throttle body (e.g. `{"error": 429}` or an empty listing payload)
- **THEN** the handler returns a `TierResult` with a real verdict (`rate_limited` for a throttle body), not `no_match`, and the cascade records an observation for the site-handler step

#### Scenario: Unclaimed URL is the only silent skip

- **WHEN** no registered handler's `matches(url)` returns `True`
- **THEN** `SiteHandlerTier` returns `no_match`, and the cascade records no observation / diagnostic row for the site-handler step

### Requirement: Site handlers receive resolved cookies

The `SiteHandlerTier` dispatch seam SHALL thread the per-fetch resolved cookies into the handler. `Handler.fetch` SHALL accept the resolved cookie set, and a handler that issues authenticated-capable requests (for example the Reddit handler's `.json` call) SHALL attach those cookies to its HTTP client. When `cookie_source == "none"` or no cookies are resolved for the request host, handlers SHALL behave exactly as before — unauthenticated, no behavior change.

#### Scenario: Reddit handler attaches resolved cookies

- **WHEN** a fetch resolves Reddit session cookies for the host and dispatches the Reddit handler
- **THEN** the handler's `.json` HTTP request carries those cookies

#### Scenario: No cookies resolved leaves handler behavior unchanged

- **WHEN** `cookie_source == "none"`, or the cookie jar resolves no cookies for the host
- **THEN** handlers issue unauthenticated requests exactly as before
