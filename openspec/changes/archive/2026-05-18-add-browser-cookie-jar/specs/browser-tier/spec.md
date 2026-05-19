## ADDED Requirements

### Requirement: Browser tier seeds context with per-fetch cookies

`BrowserTier.fetch` SHALL accept an optional `cookies_full: list[Cookie] | None = None` keyword carrying full Cookie objects (name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite). When set and non-empty, the tier SHALL call `context.add_cookies([...])` on the per-host `BrowserContext` BEFORE navigation, converting each `Cookie` to Playwright's shape:

- `name` → `name`
- `value` → `value`
- `host_key` → `domain`
- `path` → `path`
- `expires_utc` (unix seconds, None → -1 for session) → `expires`
- `is_secure` (0/1) → `secure` (bool)
- `is_httponly` (0/1) → `httpOnly` (bool)
- `samesite` (`"lax"|"strict"|"none"|None`) → `sameSite` (`"Lax"|"Strict"|"None"`); None omitted

When unset or empty, no `add_cookies` call SHALL be made (current behavior unchanged).

The seeded cookies SHALL augment any cookies already in the warm context — `add_cookies` overwrites by `(name, domain, path)` triple, which is the desired semantic when a refreshed mirror provides a newer value for an existing cookie.

#### Scenario: No add_cookies call when cookies_full is None

- **WHEN** `BrowserTier.fetch(url, cookies_full=None)` runs
- **THEN** the captured `BrowserContext.add_cookies` is not called

#### Scenario: Cookies are seeded with correct Playwright shape

- **WHEN** `BrowserTier.fetch` runs with one cookie `(name="sid", value="x", host_key=".example.com", path="/", expires_utc=None, is_secure=1, is_httponly=1, samesite="lax")`
- **THEN** `add_cookies` is called once with a list whose single element has `name="sid"`, `value="x"`, `domain=".example.com"`, `path="/"`, `expires=-1`, `secure=True`, `httpOnly=True`, `sameSite="Lax"`

#### Scenario: SameSite None omitted from Playwright payload

- **WHEN** the source cookie has `samesite=None`
- **THEN** the resulting Playwright cookie dict has no `sameSite` key

#### Scenario: add_cookies runs before navigation

- **WHEN** `BrowserTier.fetch` is invoked with non-empty cookies
- **THEN** the captured call order is `add_cookies(...)` then `page.goto(url)`; never the reverse

### Requirement: Browser tier does not log cookie values

The browser tier SHALL NOT include cookie values in any LDD event payload, structlog record, or diagnostic row. Counts and host_keys are permitted; values are not.

#### Scenario: LDD event carries no values

- **WHEN** the browser tier emits an LDD event for a fetch with 3 cookies attached
- **THEN** the captured event payload contains no value substring of any of the 3 cookies
