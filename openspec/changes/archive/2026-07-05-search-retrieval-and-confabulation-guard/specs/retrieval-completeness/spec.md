## ADDED Requirements

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
