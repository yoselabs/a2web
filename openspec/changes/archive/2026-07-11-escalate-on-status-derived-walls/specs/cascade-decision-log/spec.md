## ADDED Requirements

### Requirement: Transport and status failures escalate through the ladder

`decide_next` SHALL include `PlannerRule`s that route **ambiguous transport/status tier failures** into the escalation ladder by returning `EscalateBrowser`, so that no such failure ends the cascade without the browser (and, via the existing ladder, archive and paid) having been attempted. Each rule SHALL read the most-recent `tier_outcome` observation's `verdict`, `status_code`, and `authoritative` fields — the discriminator is the `status_code` already carried on the observation; the rules SHALL NOT require new `Verdict` members to be introduced in the tier layer.

The following tier-failure classes are **ambiguous** and SHALL escalate (each rule guarded by `browser_dispatches < 2` so it cannot re-fire past the browser cap):

- **403 forbidden** — `connection_error` with `status_code == 403`. Treated as anti-bot by default.
- **5xx server error** — `connection_error` with `status_code >= 500`.
- **other 4xx** — `connection_error` with `400 <= status_code < 500`, excluding 403 (and 404/429, which are their own verdicts).
- **timeout** — `Verdict.timeout`.
- **network/TLS drop** — `connection_error` with `status_code == 0` that is NOT a genuine DNS-resolution failure (see the DNS carve-out requirement).
- **uncorroborated 404** — `not_found` WITHOUT the `authoritative` flag.
- **exhausted 429** — `rate_limited` (retry/backoff already spent by the tier), generalized to every URL shape (not only search/listing).

These rules SHALL sit at `LOW` priority — below the `HIGH` gate-browser signal and the specific archive heuristics — so a more-specific content/gate-based decision always wins; they are the catch-all floor. They SHALL return `EscalateBrowser` (never `EscalatePaid` directly): the free self-hosted browser rung is tried first, and the existing `paid_last_resort` rule handles paid egress only after the browser cap is spent and the result is still a wall. `proxy_unavailable` (local proxy-pool exhaustion, not a site wall) SHALL NOT be swept into these rules.

Every added rule SHALL carry a unique `name` and a test pair, per the existing rule-identity contract.

#### Scenario: A 403 escalates to browser

- **WHEN** the last tier observation is `connection_error` with `status_code == 403` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: A 5xx escalates to browser

- **WHEN** the last tier observation is `connection_error` with `status_code == 502` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: A timeout escalates to browser

- **WHEN** the last tier observation is `Verdict.timeout` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: An uncorroborated 404 escalates to browser

- **WHEN** the last tier observation is `not_found` with `authoritative == False` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: An authoritative 404 does NOT escalate

- **WHEN** the last tier observation is `not_found` with `authoritative == True` (a site handler that models the site's real "gone" semantics)
- **THEN** the transport rules return `None` for this observation (the page is genuinely gone; no browser escalation)

#### Scenario: An exhausted 429 escalates on any shape

- **WHEN** the last tier observation is `rate_limited` (the tier already spent its retry/backoff) on a non-search, non-listing URL
- **THEN** `decide_next` returns `EscalateBrowser` (generalized from the prior search/listing-only render escalation)

#### Scenario: Transport rules do not fire past the browser cap

- **WHEN** any transport-failure observation is present but `browser_dispatches >= 2`
- **THEN** no transport rule returns `EscalateBrowser` (the ladder proceeds to paid / the loud terminal)

#### Scenario: A content-gate browser signal outranks the transport catch-all

- **WHEN** the log carries both a transport-failure observation and a `gate_outcome` with `escalation.next_tier == "browser"` (HIGH), with the browser budget unspent
- **THEN** the HIGH gate-browser rule's `EscalateBrowser` is what fires; the transport catch-all is not the deciding rule (same action, higher-priority source)

#### Scenario: proxy_unavailable is not swept into transport escalation

- **WHEN** the last tier observation is `proxy_unavailable` (local proxy-pool exhaustion, `status_code == 0`)
- **THEN** the transport rules return `None` (proxy exhaustion is not a site wall; it is handled at the proxy layer)

### Requirement: Genuine DNS resolution failure stays terminal, not escalated

A genuine DNS resolution failure (the domain does not resolve) SHALL be terminal — no browser, archive, or paid escalation — because a real browser resolves the same name identically; there is nothing to gain. This carve-out depends on the tier layer surfacing DNS failure as a distinct terminal `Verdict.dns_error` (adopted from the shelf `http-fetch` `FetchVerdict.dns_error`). The `network/TLS drop` transport rule (status-0 `connection_error`) SHALL fire only when the failure is NOT `dns_error`.

Until `dns_error` is available, the implementation MAY fall back to escalating all status-0 `connection_error` (a genuinely-dead domain then incurs one bounded, capped browser attempt before the loud terminal); this interim SHALL be tightened to the `dns_error` carve-out once the shelf verdict lands.

#### Scenario: NXDOMAIN does not escalate

- **WHEN** the last tier observation is `dns_error` (the domain does not resolve)
- **THEN** the transport rules return `None`; the cascade ends terminal (a real browser cannot resolve a nonexistent domain)

#### Scenario: A network drop that is not DNS still escalates

- **WHEN** the last tier observation is `connection_error` with `status_code == 0` that is NOT `dns_error` (connection reset / TLS handshake drop)
- **THEN** `decide_next` returns `EscalateBrowser` (a network-layer block may be passable by a real browser)
