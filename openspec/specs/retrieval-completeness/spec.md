# retrieval-completeness Specification

## Purpose
TBD - created by archiving change reddit-reachability-never-silent-miss. Update Purpose after archive.
## Requirements
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

#### Scenario: A thin terminal downstream of a wall prescribes the browser

- **WHEN** a fetch is refused by an upstream tier (e.g. a 403) and a later tier returns a thin body the gate resolves to `length_floor`, with no gone/unreachable evidence (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true` and the critical `try_user_browser` hint

#### Scenario: Proxy exhaustion prescribes the browser

- **WHEN** a fetch ends `failed` on `proxy_unavailable` with no gone/unreachable evidence (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true` and the `try_user_browser` hint (the caller's own browser bypasses a2web's proxy entirely)

#### Scenario: A genuinely-gone URL is not dressed as a wall

- **WHEN** a fetch ends on `dns_error` (outcome `unreachable`) or an authoritative `not_found` (outcome `gone_confirmed`)
- **THEN** the response is `status: failed` but carries NO `try_user_browser` hint and is NOT `retrieval_incomplete` — it honestly reports the domain/resource as gone, not "behind a wall"

#### Scenario: A retrieved non-HTML resource is not a wall

- **WHEN** a fetch ends on `content_type_mismatch` (outcome `unreachable` — a non-HTML resource was retrieved)
- **THEN** the response does NOT carry the `try_user_browser` hint (a browser will not extract it better)

#### Scenario: A bad paid key keeps its own hint

- **WHEN** a fetch ends on `paid_auth_error` (outcome `operator_error`)
- **THEN** the response carries the dedicated `paid_auth_error` hint (NOT `try_user_browser`) and is `retrieval_incomplete: true`

#### Scenario: The hint is emitted once, at a single chokepoint

- **WHEN** a fetch fails via a bodyless transport path OR a body-bearing content wall
- **THEN** the terminal hint is emitted exactly once by the `classify_terminal` chokepoint, and a handler's eager emission is not duplicated

### Requirement: Critical browser-escalation hint

On a terminal `wall` outcome, the response SHALL include `OperatorHint(code="try_user_browser")` at `severity: critical` with imperative, capability-generic wording. The hint SHALL NOT name a specific browser product, and SHALL NOT be emitted on any `not_found` (`gone_confirmed` / `gone_unverified`), `unreachable`, or `operator_error` outcome.

#### Scenario: Critical hint on wall

- **WHEN** a fetch terminates on `anti_bot` (outcome `wall`)
- **THEN** a `try_user_browser` critical hint is present

#### Scenario: No critical hint on a dead URL

- **WHEN** a fetch terminates on a corroborated or unverified 404
- **THEN** NO `try_user_browser` hint is present (the caller is not commanded to open a nonexistent page)

### Requirement: Eager for Reddit, late for unknown walls
For Reddit walled fetches (where the full tier ladder is known to fail), the hint SHALL be emitted eagerly by the handler without spending the browser tier. For other hosts, the hint SHALL be emitted late — only after the tier ladder is exhausted — so tiers with real hit rates are not skipped.

#### Scenario: Reddit emits eagerly
- **WHEN** a Reddit fetch is walled at the handler
- **THEN** the critical hint is emitted without dispatching the browser tier

#### Scenario: Unknown host emits late
- **WHEN** an unknown host is walled at the raw tier
- **THEN** the ladder continues (jina/archive/browser) and the hint is emitted only if all tiers fail

### Requirement: Unrecognized Reddit shape hint
When a Reddit URL matches no supported shape, the handler SHALL emit a hint listing the API-convertible shapes rather than silently falling through.

#### Scenario: Weird Reddit URL gets a breadcrumb
- **WHEN** a Reddit URL of an unrecognized shape is fetched
- **THEN** the response includes a hint naming the supported shapes (thread, permalink, search, top/new listing, user)

### Requirement: Obstacle-flagged ask answers surface as retrieval-incomplete

The never-silently-miss floor SHALL extend to the confabulation case: when an `ask` extractor reports an `obstacle` in `{empty, blocked}` — indicating the page carried no answer-bearing content matching the request (an SPA shell, a stale/unrelated render, or a wall the extractor still summarized) — the orchestrator SHALL FIRST attempt one paid render of the original URL to complete retrieval, provided a paid tier is keyed and no paid render was already spent (`paid_dispatches < 1`). When the render produces new content, the answer is re-extracted over it and the fresh `obstacle` is authoritative.

`retrieval_incomplete = true` (plus a `retrieval_incomplete` operator hint naming the likely cause) MUST be set when the obstacle survives: no paid tier is keyed, the render produced nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`. A fluent-but-unfounded answer with a surviving obstacle MUST NOT be presented as a confident, complete result. `paywalled` / `error` obstacles cap confidence but do NOT trigger a render (a render won't clear a paywall; archive owns that path).

**Structured-grounded carve-out.** An `obstacle: "empty"` SHALL NOT set `retrieval_incomplete` and SHALL NOT emit the critical `retrieval_incomplete` hint when ALL of: (a) the `ok` verdict was promoted by the `structured-data-answers` length-floor exemption (the page was thin and its only answer source was an answer-bearing structured candidate — surfaced as an internal `structured_grounded` signal on the response), AND (b) the extractor returned a **non-empty** answer. In that population a non-empty answer is structured-grounded by construction, so the `empty` obstacle is a false positive. The honest hedge is retained — `confidence` stays `low` for these answers — so the caller is still directed to verify, via a low-confidence answer rather than a klaxon that contradicts the delivered answer. This carve-out applies ONLY to `empty`: a `blocked` obstacle, and any obstacle on a page whose `ok` did NOT come from the structured exemption, keep today's incompleteness behavior. An empty answer is out of scope (the `extraction_empty` guard still hard-fails it).

#### Scenario: Empty obstacle triggers a paid render before declaring incomplete

- **WHEN** an `ask` fetch reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches one paid render of the original URL and re-extracts the answer over the rendered content
- **AND** if the render yields answer-bearing content (fresh obstacle clears), the response is `ok` with the real answer and is NOT flagged incomplete

#### Scenario: Surviving obstacle after render is flagged incomplete

- **WHEN** the paid render produces nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`
- **THEN** the response sets `retrieval_incomplete = true`, carries the `retrieval_incomplete` operator hint, and `confidence` is `low`

#### Scenario: No paid tier keyed still flags incomplete (loud miss)

- **WHEN** an `ask` fetch reports `obstacle: "empty"` but no paid tier is registered
- **AND** the `ok` verdict did NOT come from the structured-answer exemption (a normal prose page)
- **THEN** no render is attempted, and the response sets `retrieval_incomplete = true` with the critical hint (never-silently-miss holds)

#### Scenario: A prior paid render suppresses the obstacle render

- **WHEN** an `ask` fetch already spent its paid dispatch (`paid_dispatches == 1`, e.g. a gate wall or handler `escalate_to_render`) and the extractor still reports `obstacle ∈ {empty, blocked}`
- **THEN** no second paid render is attempted, and the surviving obstacle flags `retrieval_incomplete`

#### Scenario: Paywalled/error obstacles do not trigger a render

- **WHEN** an `ask` fetch reports `obstacle: "paywalled"` or `obstacle: "error"`
- **THEN** no obstacle-driven render is dispatched, and `confidence` is capped to `low` (the wall/verdict machinery owns paywall completeness)

#### Scenario: Structured-grounded non-empty answer is not flagged incomplete

- **WHEN** an `ask` fetch on a thin page was promoted to `ok` by the structured-answer length-floor exemption (`structured_grounded`), the extractor returns a non-empty answer, and reports `obstacle: "empty"`
- **THEN** `retrieval_incomplete` stays `false`, no critical `retrieval_incomplete` hint is emitted, and `confidence` is `low` (the answer is delivered with an honest hedge, not a contradiction)

#### Scenario: Structured-grounded EMPTY answer still hard-fails

- **WHEN** a structured-exemption-promoted page yields an empty answer
- **THEN** the `extraction_empty` guard fires (`status: failed` + `retrieval_incomplete`), unchanged by the carve-out

#### Scenario: The empty-answer guard covers thin promoted pages

- **WHEN** an `ask` on a `structured_grounded` page has `extraction_meta` set but an empty extracted answer, and `content_md` is below the 500-char `extraction_empty` length threshold
- **THEN** `extraction_empty` STILL fires (`status: failed` + `retrieval_incomplete`) — the `>500` threshold, which assumed thin pages already failed at the length floor, is extended with `or structured_grounded` so a promoted thin page cannot return an `ok` empty answer (ADR-0009 never-silently-miss)

#### Scenario: A blocked obstacle on a promoted page is still flagged

- **WHEN** a structured-exemption-promoted page reports `obstacle: "blocked"` (not `empty`)
- **THEN** the carve-out does NOT apply and `retrieval_incomplete = true` with the critical hint

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

