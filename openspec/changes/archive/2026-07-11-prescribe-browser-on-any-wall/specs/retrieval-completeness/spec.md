## MODIFIED Requirements

### Requirement: An unfetched URL is never mistakable for success

Every fetch that ends `status: failed` SHALL be treated as a retrieval miss and prescribe the caller's own browser — EXCEPT a small, explicit set of **genuine-gone** terminals where a browser genuinely cannot help. This is a single systematic floor, not a per-verdict whitelist: the response SHALL carry the critical `try_user_browser` operator hint and `retrieval_incomplete: true` whenever the resolved verdict is not `ok` and is not a genuine-gone terminal. The wire serializer SHALL NOT present such a fetch as a soft, complete-looking answer.

The **genuine-gone terminals** (the only `failed` outcomes that do NOT prescribe a browser) are:

- `dns_error` — the domain does not resolve; a real browser resolves the same name identically. Reported as genuinely unresolvable, NOT `retrieval_incomplete`.
- an **authoritative** `not_found` — a site handler that models the site's real "gone" semantics (a deleted item). Reported as genuinely gone, NOT `retrieval_incomplete`.
- `content_type_mismatch` — a non-HTML resource WAS retrieved (a PDF/image); a browser will not extract it better. Not a wall; no `try_user_browser`.
- `paid_auth_error` — carries its OWN dedicated `paid_auth_error` hint (a keyed paid tier's bad credentials, an operator error) instead of `try_user_browser`; it IS still `retrieval_incomplete`.

Every OTHER failed verdict SHALL prescribe the browser — the content walls (`block_page_detected`, `anti_bot`, `paywall`, `blank_page`), the transport failures (`connection_error`, `timeout`, `rate_limited`, uncorroborated `not_found`), AND the verdicts that fell through the prior whitelists (`length_floor`, `proxy_unavailable`, `other`). A `length_floor` (or any thin/failed terminal) that arises downstream of a wall — e.g. a 403 followed by a thin reader response — SHALL therefore prescribe the browser by construction, without the orchestrator needing to remember which earlier verdict started the cascade.

The hint SHALL remain capability-generic (it SHALL NOT name a specific browser product); it prescribes that the caller open the URL in its own real-browser tool (which passes walls that all server-side and headless automation are blocked by) OR explicitly tell the user the source could not be retrieved. Emission SHALL occur once per fetch at a single chokepoint that runs regardless of which internal phase terminated the cascade, and SHALL NOT double-emit when a handler already attached the hint eagerly.

#### Scenario: Any content wall prescribes the browser
- **WHEN** a fetch terminates on `block_page_detected`, `anti_bot`, `paywall`, or `blank_page`
- **THEN** the response carries `retrieval_incomplete: true`, `status: failed`, and the critical `try_user_browser` hint

#### Scenario: A thin terminal downstream of a wall prescribes the browser
- **WHEN** a fetch is refused by an upstream tier (e.g. a 403) and a later tier returns a thin body the gate resolves to `length_floor`, so the fetch ends `failed` with `length_floor`
- **THEN** the response carries `retrieval_incomplete: true` and the critical `try_user_browser` hint — the miss is loud even though `length_floor` was on no prior wall whitelist

#### Scenario: Proxy exhaustion prescribes the browser
- **WHEN** a fetch ends `failed` on `proxy_unavailable` (the proxy pool is exhausted)
- **THEN** the response carries `retrieval_incomplete: true` and the `try_user_browser` hint (the caller's own browser bypasses a2web's proxy entirely)

#### Scenario: A genuinely-gone URL is not dressed as a wall
- **WHEN** a fetch ends on `dns_error` or an authoritative `not_found`
- **THEN** the response is `status: failed` but carries NO `try_user_browser` hint and is NOT `retrieval_incomplete` — it honestly reports the domain/resource as gone, not "behind a wall"

#### Scenario: A retrieved non-HTML resource is not a wall
- **WHEN** a fetch ends on `content_type_mismatch` (a non-HTML resource was retrieved)
- **THEN** the response does NOT carry the `try_user_browser` hint (a browser will not extract it better)

#### Scenario: A bad paid key keeps its own hint
- **WHEN** a fetch ends on `paid_auth_error`
- **THEN** the response carries the dedicated `paid_auth_error` hint (NOT `try_user_browser`) and is `retrieval_incomplete: true`

#### Scenario: The hint is emitted once, at a single chokepoint
- **WHEN** a fetch fails via a bodyless transport path (early-returning before the gate) OR via a body-bearing content wall
- **THEN** the `try_user_browser` hint is emitted exactly once by the same systematic floor, and a handler's eager emission is not duplicated
