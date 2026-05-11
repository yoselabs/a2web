# site-handlers (delta)

## ADDED Requirements

### Requirement: Reddit handler falls back to old.reddit.com on .json failure

The Reddit handler SHALL attempt a fallback against `old.reddit.com` when its primary `.json` request:

- returns HTTP 404, OR
- returns HTTP 200 but with an empty `data.children` array (e.g. removed / private / quarantined threads), OR
- fails to JSON-decode the body

The fallback SHALL:

1. Construct `https://old.reddit.com<path>` from the original URL's path component (no `.json` suffix).
2. Issue an HTTP GET with the standard user agent and 10 s timeout.
3. On HTTP 200, render the HTML via trafilatura into `Rendered` with the same shape as the JSON path (title, byline, content_md, headings).
4. On any non-200, return `TierResult` with the appropriate `Verdict` (not_found, rate_limited, connection_error) — do NOT escalate further from inside the handler.

The fallback path SHALL NOT be attempted when the `.json` path succeeded with a non-empty thread.

#### Scenario: thread with 404 on .json falls back to old.reddit

- **WHEN** the handler fetches a Reddit URL and the `.json` GET returns HTTP 404
- **THEN** the handler makes one additional GET to `old.reddit.com<path>`
- **AND** on HTTP 200, returns a populated `Rendered` with `content_md` derived from old.reddit's server-rendered HTML

#### Scenario: successful .json path is not double-fetched

- **WHEN** the `.json` GET returns 200 with a non-empty thread
- **THEN** the handler does NOT issue a request to `old.reddit.com`

### Requirement: Twitter / X handler via configurable Nitter instances

A new handler `TwitterHandler` SHALL be registered for hosts `x.com`, `twitter.com`, `www.x.com`, `www.twitter.com` matching paths of the form `/<user>/status/<id>(/.*)?`.

Behavior:

1. Read the `nitter_instances: list[str]` setting from `AppSettings` (env `A2WEB_NITTER_INSTANCES`, comma-separated; also from YAML config).
2. If the list is empty, `matches(url)` returns `False` (the handler effectively disabled — fetch falls through to other tiers without an error).
3. If the list is non-empty, `fetch(url, state)`:
   - Iterates the list in a per-fetch randomized order.
   - Skips any instance currently in `purgatory` quarantine (reuse the existing breaker infra).
   - For each instance: `GET <instance>/<user>/status/<id>` with 5 s timeout.
   - On HTTP 200: parse via trafilatura, return `TierResult` with `Rendered` populated.
   - On timeout / 4xx / 5xx: trip the instance's breaker, continue rotation.
   - If all instances fail: return `TierResult(no_match=True)` — fall-through to raw + browser tiers.

#### Scenario: empty Nitter list disables the handler silently

- **GIVEN** `nitter_instances` is empty
- **WHEN** the handler's `matches(url)` is called for an x.com status URL
- **THEN** `matches` returns `False`
- **AND** the orchestrator proceeds to raw + escalation tiers as if the handler did not exist

#### Scenario: first working instance returns content

- **GIVEN** `nitter_instances` is `["nitter.example.com", "nitter2.example.com"]`
- **WHEN** the handler fetches an x.com status URL and `nitter.example.com` returns HTTP 200 with the tweet HTML
- **THEN** the handler returns `TierResult` with `pre_rendered.content_md` containing the tweet text
- **AND** does NOT call `nitter2.example.com`

#### Scenario: failed instance trips its breaker; rotation continues

- **GIVEN** two Nitter instances configured and the first times out
- **WHEN** the handler iterates
- **THEN** the first instance's circuit breaker records a failure
- **AND** the handler tries the second instance
- **AND** returns the second instance's content on success
