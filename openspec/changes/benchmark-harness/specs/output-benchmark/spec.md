## ADDED Requirements

### Requirement: the benchmark is package-resident and re-runnable

The benchmark SHALL live inside the maintained package at `src/a2web/llm_eval/`, be type-checked and test-covered, and be invocable by a single command. It SHALL NOT be implemented as dated throwaway scripts outside the package. Re-running the benchmark after an envelope change SHALL require no edits to the harness.

#### Scenario: the benchmark runs from one command

- **WHEN** an operator runs the benchmark command (`make bench` / `python -m a2web.llm_eval`)
- **THEN** the full corpus × systems matrix runs and a dated report is written, with no manual per-URL steps

#### Scenario: an envelope change does not require harness edits

- **WHEN** the a2web response envelope changes in a spec-conformant way
- **THEN** the benchmark still runs unchanged, and any contract regression is reported by the data-contract axis rather than crashing the harness

### Requirement: the benchmark scores four axes per cell

For each (URL, system) cell the benchmark SHALL record four axes: answer quality (judge score against per-question criteria), token cost (tokens of the response envelope the agent must read), output clarity (how cleanly an agent can act on the output), and data-contract conformance. All four SHALL appear in the run report.

#### Scenario: a cell carries all four axes

- **WHEN** the benchmark scores one (URL, system) cell
- **THEN** the report row for that cell carries an answer-quality score, a token-cost number, an output-clarity score, and a data-contract-conformance result

#### Scenario: token cost measures the envelope

- **WHEN** the token-cost axis is recorded for an a2web system
- **THEN** it is the token count of the response envelope the agent receives, broken down by field — not the tokens of any internal LLM call

### Requirement: data-contract conformance is checked deterministically

The data-contract axis SHALL be a deterministic, non-LLM assertion that the a2web response envelope obeys its field-presence rules: `tier`, `url`, and `status` present only when they deviate from their default; the `debug` object present only under `debug=True`; `next_links` well-shaped when present. A violation SHALL be reported as a contract failure for that cell.

#### Scenario: a conformant envelope passes

- **WHEN** an a2web envelope obeys every field-presence rule
- **THEN** the data-contract axis for that cell reports conformance

#### Scenario: a deviation-field leak fails the axis

- **WHEN** an a2web envelope carries `tier`, `url`, or `status` at a non-deviating value, or carries `debug` without `debug=True`
- **THEN** the data-contract axis reports a contract failure naming the offending field

### Requirement: next_links candidate quality is scored on listing URLs

For listing-style corpus URLs the benchmark SHALL apply a `next_links_picked_correctly` judge axis assessing whether the `next_links` candidates are the right "what to fetch next" set for the task. Non-listing URLs SHALL NOT be scored on this axis.

#### Scenario: a listing URL is scored on next_links

- **WHEN** the benchmark runs a listing-style URL (e.g. a Reddit or HN listing, a PyPI or gh-trending page) through an a2web system
- **THEN** the report records a `next_links_picked_correctly` score for that cell

#### Scenario: a non-listing URL skips the axis

- **WHEN** the benchmark runs a permalink or article URL that has no drilldown layer
- **THEN** the `next_links_picked_correctly` axis is not scored for that cell

### Requirement: the corpus covers tricky scenarios

The benchmark corpus SHALL include the cases that break naive fetchers — Reddit comment threads, Hacker News comment/item pages, and index/listing pages — in addition to clean-HTML, gated, and SPA classes. Each corpus entry SHALL carry a task and pass/fail `criteria` phrased against stable structural facts so the entry survives page-content rotation.

#### Scenario: the corpus includes comment and listing pages

- **WHEN** the benchmark corpus is loaded
- **THEN** it contains at least one Reddit comment thread, one Hacker News comment/item page, and one index/listing page, each with a task and non-empty criteria

### Requirement: the benchmark compares against a WebFetch baseline without an API key

The benchmark SHALL include Claude Code's WebFetch as a baseline system run head-to-head with the a2web systems, produced automatically by the in-process `WebFetchBaseline` reproduction. The benchmark SHALL run on the `claude-code` provider (OAuth subscription) by default and SHALL NOT require `ANTHROPIC_API_KEY`; it MAY fall back to an API-key provider when the subscription provider is unavailable.

#### Scenario: the run includes the WebFetch baseline automatically

- **WHEN** the benchmark runs in its default mode
- **THEN** the report carries WebFetch-baseline rows alongside the a2web-system rows, with no interactive per-URL step

#### Scenario: the benchmark runs without an API key

- **WHEN** the benchmark is started with no `ANTHROPIC_API_KEY` set and Claude Code is logged in
- **THEN** the suite runs to completion using the `claude-code` provider for both the reader and the judge
