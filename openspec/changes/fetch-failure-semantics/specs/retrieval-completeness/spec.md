## ADDED Requirements

### Requirement: Terminal outcome is a pure projection of the decision log

The caller-facing terminal signals (`retrieval_incomplete`, the wall/gone/error hint, and its `severity`) SHALL be derived by a single pure function `classify_terminal(observations, resolved_verdict) -> TerminalOutcome` that reads the **observation log**, not merely the resolved verdict projection. `TerminalOutcome` SHALL be a closed enum: `wall`, `gone_confirmed`, `gone_unverified`, `operator_error`, `unreachable`. The function SHALL be pure, total, and free of I/O — the terminal-story sibling of the forward planner. It replaces the prior `_is_genuine_gone` / `_prescribe_browser_on_wall` predicate pair.

Because it reads the log, evidence recorded by any tier (e.g. two independent tiers observing HTTP 404) SHALL be reachable to the classifier even when the *resolved* verdict differs — the failure mode where a corroborating observation existed but a predicate keyed on the projection could not see it SHALL NOT recur.

#### Scenario: Corroborating observations are reachable

- **WHEN** the log holds `raw: not_found (404)` and `browser: not_found (404)` but the resolved verdict is some other value (e.g. a mis-won thin tier)
- **THEN** `classify_terminal` returns `gone_confirmed` from the corroborated 404 observations, not a `wall` derived from the resolved verdict

#### Scenario: Total over outcomes

- **WHEN** `classify_terminal` is evaluated over the space of observation shapes
- **THEN** every input maps to exactly one `TerminalOutcome`

### Requirement: not_found is corroboration-keyed, not source-keyed

An HTTP `not_found` (404) SHALL be classified by what the cascade OBSERVED, since the cascade already dispatches the browser on an uncorroborated 404 (the soft-404 hypothesis is tested, not assumed):

- an HTTP 404 that a browser render **also** returned as 404 → `gone_confirmed`: reported as a likely dead/wrong URL confirmed by a rendered browser, with an `content_not_found` hint at `severity: info`, NO `try_user_browser`, NO soft-404 caveat, and NOT `retrieval_incomplete`;
- an HTTP 404 whose browser check **could not complete** (browser budget already spent, browser pool unavailable, or the browser returned something other than 404) → `gone_unverified`: reported as a likely dead URL with a `content_not_found` hint at `severity: warning` that discloses a SMALL residual chance a bot-defense soft-404 is masking real content and offers the caller's own browser as the residual test; `retrieval_incomplete: true`;
- a handler-**authoritative** `not_found` (a site handler modelling real "gone" semantics) → `gone_confirmed`, silent, NO caveat (definitively gone).

The critical `try_user_browser` hint SHALL NOT be emitted for any `not_found` terminal.

#### Scenario: Browser-corroborated 404 is honest, not alarmed

- **WHEN** a dead URL returns 404 at the raw tier and our own browser render also returns 404
- **THEN** the response is `status: failed` with `content_not_found` at `severity: info`, carries NO `try_user_browser`, and is NOT `retrieval_incomplete` — it reports a likely dead/wrong URL, confirmed

#### Scenario: Unverified 404 discloses the soft-404 residual

- **WHEN** a URL returns 404 but the browser soft-404 check could not run (budget spent / pool down)
- **THEN** the response carries `content_not_found` at `severity: warning` naming the small soft-404 possibility and the browser escape hatch, and IS `retrieval_incomplete`

### Requirement: Hint severity encodes retrieval confidence

`OperatorHint.severity` SHALL carry a confidence semantics: `info` = a verified fact (e.g. a browser-corroborated gone URL), `warning` = the check could not be completed (residual uncertainty the caller may resolve), `critical` = every recovery path was attempted and a wall was hit. A dead URL SHALL NOT receive a `critical` signal.

#### Scenario: A dead URL is never critical

- **WHEN** a fetch terminates on a corroborated or unverified `not_found`
- **THEN** no `critical` hint is emitted; the severity is `info` or `warning` respectively

## MODIFIED Requirements

### Requirement: An unfetched URL is never mistakable for success

Every fetch that ends `status: failed` SHALL be treated as a retrieval miss and prescribe the caller's own browser — EXCEPT the terminals that `classify_terminal` resolves to `gone_confirmed`, `unreachable`, or `operator_error`, where a browser genuinely cannot help. This remains a single systematic floor, expressed as the output of `classify_terminal(observations, resolved_verdict)` (not a whitelist over the resolved verdict): the response SHALL carry the critical `try_user_browser` hint and `retrieval_incomplete: true` exactly when the outcome is `wall`.

The outcomes that do NOT prescribe the browser are:

- `unreachable` — `dns_error` (the domain does not resolve) or `content_type_mismatch` (a non-HTML resource WAS retrieved). Reported as genuinely unreachable/retrieved-non-HTML, NOT a wall.
- `gone_confirmed` — a handler-authoritative `not_found`, OR an HTTP 404 a browser render corroborated. Reported honestly as gone/dead, NOT `retrieval_incomplete`, with a `content_not_found` info hint rather than `try_user_browser`.
- `operator_error` — `paid_auth_error` keeps its own dedicated hint; it IS still `retrieval_incomplete`.

`gone_unverified` (an HTTP 404 whose soft-404 check could not complete) is `retrieval_incomplete` but carries the `content_not_found` WARNING (with the browser escape hatch), NOT the CRITICAL `try_user_browser`. Every `wall` outcome — the content walls (`block_page_detected`, `anti_bot`, `paywall`, `blank_page`) and the transport/thin terminals that are not classified gone/unreachable/operator (`connection_error`, `timeout`, `rate_limited`, `length_floor`, `proxy_unavailable`, `other`) — SHALL prescribe the browser after the escalation ladder is exhausted. Emission SHALL occur once per fetch at the single chokepoint that consumes `classify_terminal`, and SHALL NOT double-emit when a handler attached a hint eagerly.

#### Scenario: Any content wall prescribes the browser

- **WHEN** a fetch terminates on `block_page_detected`, `anti_bot`, `paywall`, or `blank_page` (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true`, `status: failed`, and the critical `try_user_browser` hint

#### Scenario: A dead URL is reported gone, not walled

- **WHEN** a fetch ends on a corroborated HTTP 404 (outcome `gone_confirmed`)
- **THEN** the response is `status: failed` with a `content_not_found` info hint, NO `try_user_browser`, and NOT `retrieval_incomplete`

#### Scenario: A thin terminal downstream of a wall still prescribes the browser

- **WHEN** a fetch is refused by an upstream tier (e.g. a 403) and a later tier returns a thin body the gate resolves to `length_floor`, with no gone/unreachable evidence (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true` and the critical `try_user_browser` hint

#### Scenario: The hint is emitted once, at a single chokepoint

- **WHEN** a fetch fails via a bodyless transport path OR a body-bearing content wall
- **THEN** the terminal hint is emitted exactly once by the `classify_terminal` chokepoint, and a handler's eager emission is not duplicated

### Requirement: Critical browser-escalation hint

On a terminal `wall` outcome, the response SHALL include `OperatorHint(code="try_user_browser")` at `severity: critical` with imperative, capability-generic wording. The hint SHALL NOT name a specific browser product, and SHALL NOT be emitted on any `not_found` (`gone_confirmed` / `gone_unverified`), `unreachable`, or `operator_error` outcome.

#### Scenario: Critical hint on wall only

- **WHEN** a fetch terminates on `anti_bot` (outcome `wall`)
- **THEN** a `try_user_browser` critical hint is present

#### Scenario: No critical hint on a dead URL

- **WHEN** a fetch terminates on a corroborated or unverified 404
- **THEN** NO `try_user_browser` hint is present (the caller is not commanded to open a nonexistent page)
