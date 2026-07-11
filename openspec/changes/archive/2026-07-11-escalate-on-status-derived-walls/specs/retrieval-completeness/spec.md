## MODIFIED Requirements

### Requirement: An unfetched URL is never mistakable for success

When a fetch ends in a terminal `paywall`, `block_page_detected`, or `anti_bot` verdict, the response SHALL carry an explicit `retrieval_incomplete` signal and `status: failed`. The wire serializer SHALL NOT present a walled fetch as a soft, complete-looking answer.

This never-silently-miss floor SHALL also cover **transport/status walls**: a fetch that ends on an ambiguous transport/status failure — a 403, a 5xx, an `other 4xx`, a `timeout`, a non-DNS connection/TLS drop, an uncorroborated 404, or an exhausted 429 — SHALL first be routed through the escalation ladder (`EscalateBrowser` → archive → `EscalatePaid`) before any terminal is declared. Only if the ladder is exhausted and the URL is still not retrieved does the fetch end terminal, carrying the same loud incompleteness envelope (`status: failed`, `retrieval_incomplete`, populated diagnostics + narrative, and the critical `try_user_browser` hint). A transport/status failure SHALL NOT end the cascade before the browser (and, where a key is configured, paid) rung has been attempted — the ladder is *attempted* for these failures exactly as for content-gated walls.

Two transport/status outcomes are deliberately excluded from escalation and MAY end terminal directly (they are not "unfetched behind a wall"): a genuine DNS resolution failure (`dns_error` — the domain does not resolve), and an **authoritative** `not_found` (a site handler that models the site's real "gone" semantics).

#### Scenario: Walled fetch marks incompleteness
- **WHEN** a fetch terminates on `block_page_detected`
- **THEN** the response carries `retrieval_incomplete` and `status: failed`, not a low-confidence "answer"

#### Scenario: A transport wall is escalated before the terminal fires
- **WHEN** a fetch's free tiers all end on a 403 / 5xx / timeout / uncorroborated-404 and the browser budget is unspent
- **THEN** the browser rung (and, if still walled, archive/paid) is attempted BEFORE any terminal — the ladder runs for the transport failure, not only for content-gated walls

#### Scenario: An exhausted transport wall ends in the loud terminal
- **WHEN** the escalation ladder is exhausted for a transport/status failure and the URL is still not retrieved
- **THEN** the response ends `status: failed` with `retrieval_incomplete`, populated diagnostics + narrative, and the critical `try_user_browser` hint (the ADR-0009 floor is unchanged — only what reaches it is widened)

#### Scenario: A genuinely-gone URL is not dressed as a wall
- **WHEN** a fetch ends on `dns_error` (domain does not resolve) or an authoritative `not_found`
- **THEN** no browser/archive/paid escalation is attempted and the response reports the genuine not-found / unresolvable outcome (not a "behind a wall" incompleteness)
