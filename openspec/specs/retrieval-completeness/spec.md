# retrieval-completeness Specification

## Purpose
TBD - created by archiving change reddit-reachability-never-silent-miss. Update Purpose after archive.
## Requirements
### Requirement: An unfetched URL is never mistakable for success
When a fetch ends in a terminal `paywall`, `block_page_detected`, or `anti_bot` verdict, the response SHALL carry an explicit `retrieval_incomplete` signal and `status: failed`. The wire serializer SHALL NOT present a walled fetch as a soft, complete-looking answer.

#### Scenario: Walled fetch marks incompleteness
- **WHEN** a fetch terminates on `block_page_detected`
- **THEN** the response carries `retrieval_incomplete` and `status: failed`, not a low-confidence "answer"

### Requirement: Critical browser-escalation hint
On a terminal wall verdict, the response SHALL include `OperatorHint(code="try_user_browser")` at `severity: critical` with imperative, capability-generic wording instructing the caller to either open the URL in a real-browser tool OR explicitly tell the user the source could not be retrieved. The hint SHALL NOT name a specific browser product.

#### Scenario: Critical hint on wall
- **WHEN** a fetch terminates on `anti_bot`
- **THEN** a `try_user_browser` critical hint is present with imperative wording and no product-specific tool name

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

The never-silently-miss floor SHALL extend to the confabulation case: when an `ask` extractor reports an `obstacle` in `{empty, blocked}` — indicating the page carried no answer-bearing content matching the request (an SPA shell, a stale/unrelated render, or a wall the extractor still summarized) — the response MUST set `retrieval_incomplete = true` and carry a `retrieval_incomplete` operator hint naming the likely cause. This closes the gap left by the extraction-empty guard, which only fires when the answer text is literally empty; a fluent-but-unfounded answer with an `obstacle` MUST NOT be presented as a confident, complete result.

#### Scenario: Fluent-but-empty answer is flagged incomplete

- **WHEN** an `ask` fetch returns a non-empty answer over rendered content but the extractor reports `obstacle: "empty"`
- **THEN** the response sets `retrieval_incomplete = true`
- **AND** carries an operator hint with code `retrieval_incomplete` describing the likely cause (e.g. SPA shell / stale or unrelated page)
- **AND** `confidence` is `low`

#### Scenario: Blocked obstacle is flagged incomplete

- **WHEN** an `ask` fetch reports `obstacle: "blocked"`
- **THEN** the response sets `retrieval_incomplete = true` and carries the `retrieval_incomplete` operator hint

#### Scenario: Paywalled/error obstacles cap confidence without forcing incomplete here

- **WHEN** an `ask` fetch reports `obstacle: "paywalled"` or `obstacle: "error"`
- **THEN** `confidence` is capped to `low`
- **AND** `retrieval_incomplete` is not forced by this requirement (the existing wall/verdict machinery owns the incomplete signal for true walls)

#### Scenario: Healthy answer is not flagged

- **WHEN** an `ask` fetch returns an answer and the extractor omits `obstacle`
- **THEN** `retrieval_incomplete` remains unset and no `retrieval_incomplete` hint is added

