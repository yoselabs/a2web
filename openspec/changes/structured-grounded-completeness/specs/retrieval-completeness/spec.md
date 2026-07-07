## MODIFIED Requirements

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
