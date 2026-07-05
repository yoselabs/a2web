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

The never-silently-miss floor SHALL extend to the confabulation case: when an `ask` extractor reports an `obstacle` in `{empty, blocked}` — indicating the page carried no answer-bearing content matching the request (an SPA shell, a stale/unrelated render, or a wall the extractor still summarized) — the orchestrator SHALL FIRST attempt one paid render of the original URL to complete retrieval, provided a paid tier is keyed and no paid render was already spent (`paid_dispatches < 1`). When the render produces new content, the answer is re-extracted over it and the fresh `obstacle` is authoritative.

`retrieval_incomplete = true` (plus a `retrieval_incomplete` operator hint naming the likely cause) MUST be set when the obstacle survives: no paid tier is keyed, the render produced nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`. A fluent-but-unfounded answer with a surviving obstacle MUST NOT be presented as a confident, complete result. `paywalled` / `error` obstacles cap confidence but do NOT trigger a render (a render won't clear a paywall; archive owns that path).

#### Scenario: Empty obstacle triggers a paid render before declaring incomplete

- **WHEN** an `ask` fetch reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches one paid render of the original URL and re-extracts the answer over the rendered content
- **AND** if the render yields answer-bearing content (fresh obstacle clears), the response is `ok` with the real answer and is NOT flagged incomplete

#### Scenario: Surviving obstacle after render is flagged incomplete

- **WHEN** the paid render produces nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`
- **THEN** the response sets `retrieval_incomplete = true`, carries the `retrieval_incomplete` operator hint, and `confidence` is `low`

#### Scenario: No paid tier keyed still flags incomplete (loud miss)

- **WHEN** an `ask` fetch reports `obstacle: "empty"` but no paid tier is registered
- **THEN** no render is attempted, and the response sets `retrieval_incomplete = true` with the critical hint (never-silently-miss holds)

#### Scenario: A prior paid render suppresses the obstacle render

- **WHEN** an `ask` fetch already spent its paid dispatch (`paid_dispatches == 1`, e.g. a gate wall or handler `escalate_to_render`) and the extractor still reports `obstacle ∈ {empty, blocked}`
- **THEN** no second paid render is attempted, and the surviving obstacle flags `retrieval_incomplete`

#### Scenario: Paywalled/error obstacles do not trigger a render

- **WHEN** an `ask` fetch reports `obstacle: "paywalled"` or `obstacle: "error"`
- **THEN** no obstacle-driven render is dispatched, and `confidence` is capped to `low` (the wall/verdict machinery owns paywall completeness)

