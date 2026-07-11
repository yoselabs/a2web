## MODIFIED Requirements

### Requirement: An unfetched URL is never mistakable for success

When a fetch ends in a terminal `paywall`, `block_page_detected`, or `anti_bot` verdict, the response SHALL carry an explicit `retrieval_incomplete` signal and `status: failed`. The wire serializer SHALL NOT present a walled fetch as a soft, complete-looking answer.

This never-silently-miss floor SHALL also cover **transport/status walls**: a fetch that ends on an ambiguous transport/status failure — a 403, a 5xx, an `other 4xx`, a `timeout`, a non-DNS connection/TLS drop, an uncorroborated 404, or an exhausted 429 — SHALL first be routed through the escalation ladder (`EscalateBrowser` → archive → `EscalatePaid`) before any terminal is declared. Only if the ladder is exhausted and the URL is still not retrieved does the fetch end terminal, carrying the same loud incompleteness envelope (`status: failed`, `retrieval_incomplete`, populated diagnostics + narrative, and the critical `try_user_browser` hint). A transport/status failure SHALL NOT end the cascade before the browser (and, where a key is configured, paid) rung has been attempted — the ladder is *attempted* for these failures exactly as for content-gated walls.

This floor SHALL further cover **blank pages**: a fetch whose raw body carries near-zero visible text (verdict `blank_page`) SHALL be escalated through the browser and then the paid scraper before any terminal. A `blank_page` that survives the full ladder SHALL end `status: failed` + `retrieval_incomplete: true` with the critical `try_user_browser` hint, exactly as the other wall verdicts. A near-empty body SHALL be treated as a likely **silent anti-bot block** (a defended site serving nothing to non-browser clients while a real browser sees full content — e.g. a host that returns 403 to every bot yet renders completely in a logged-in browser), NOT assumed to be a genuinely empty resource: the two are indistinguishable from the fetcher's side, and reporting a content-rich walled page as "empty" is the worse (false-negative) error. The `blank_page` verdict is retained for diagnostics/narrative; only the operator hint is the shared `try_user_browser`.

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

#### Scenario: A blank page is escalated through browser then paid before terminating
- **WHEN** a fetch's raw body is near-empty (verdict `blank_page`) and the browser budget is unspent
- **THEN** the browser is dispatched, and if the render is still blank and a paid tier is keyed, the paid scraper is dispatched — BEFORE any terminal

#### Scenario: A surviving blank page ends failed with the try_user_browser hint
- **WHEN** the browser render AND the paid scraper both return an essentially empty body for a `blank_page` fetch
- **THEN** the response ends `status: failed` + `retrieval_incomplete: true` with the critical `try_user_browser` hint (a surviving blank body is treated as a likely silent anti-bot wall, not a genuinely empty resource)

#### Scenario: A genuinely-gone URL is not dressed as a wall
- **WHEN** a fetch ends on `dns_error` (domain does not resolve) or an authoritative `not_found`
- **THEN** no browser/archive/paid escalation is attempted and the response reports the genuine not-found / unresolvable outcome (not a "behind a wall" incompleteness)
