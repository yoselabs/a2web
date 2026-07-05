## MODIFIED Requirements

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
