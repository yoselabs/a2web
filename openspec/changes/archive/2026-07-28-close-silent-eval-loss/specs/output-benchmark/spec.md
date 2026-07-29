## MODIFIED Requirements

### Requirement: the benchmark scores four axes per cell

For each (URL, system) cell the benchmark SHALL record four axes: answer quality (judge score against per-question criteria), token cost (tokens of the response envelope the agent must read), output clarity (how cleanly an agent can act on the output), and data-contract conformance. All four SHALL appear in the run report. Each axis SHALL carry a disposition stating whether it was scored, was not applicable to the case, or was requested and left unscored — an absent score alone is not a permitted record, because it cannot distinguish a correct skip from a broken axis.

#### Scenario: a cell carries all four axes

- **WHEN** the benchmark scores one (URL, system) cell
- **THEN** the report row for that cell carries an answer-quality score, a token-cost number, an output-clarity score, and a data-contract-conformance result

#### Scenario: token cost measures the envelope

- **WHEN** the token-cost axis is recorded for an a2web system
- **THEN** it is the token count of the response envelope the agent receives, broken down by field — not the tokens of any internal LLM call

#### Scenario: an axis without a score states why

- **WHEN** any of the four axes produces no score for a cell
- **THEN** the row records whether the axis was not applicable to that case or was requested and left unscored, with a reason in the latter case

### Requirement: next_links candidate quality is scored on listing URLs

For listing-style corpus URLs the benchmark SHALL apply a `next_links_picked_correctly` judge axis assessing whether the "what to fetch next" candidates are the right set for the task. Non-listing URLs SHALL NOT be scored on this axis.

The axis SHALL read the candidate block from the field the scored system actually emits: the `query` envelope carries this set as `other_pages` (ADR-0015 folded the former `next_links` and `try_url` into it), while the `fetch_raw` envelope carries `next_links`. The harness SHALL NOT assume a single field name across systems, and a system emitting a candidate block under a name the harness does not read SHALL surface as a broken axis rather than as an unscored cell.

#### Scenario: a listing URL is scored on next_links

- **WHEN** the benchmark runs a listing-style URL (e.g. a Reddit or HN listing, a PyPI or gh-trending page) through an a2web system
- **THEN** the report records a `next_links_picked_correctly` score for that cell

#### Scenario: a non-listing URL skips the axis

- **WHEN** the benchmark runs a permalink or article URL that has no drilldown layer
- **THEN** the `next_links_picked_correctly` axis is not scored for that cell, and the cell's disposition for the axis is `not_applicable`

#### Scenario: the query envelope's candidate set is read under its own name

- **WHEN** a listing URL is scored through the `query` path, whose envelope exposes the candidate set as `other_pages`
- **THEN** the axis reads that block and scores the cell

#### Scenario: an envelope rename cannot silently void the axis

- **WHEN** the field carrying the candidate set is renamed and the harness no longer finds it on any requested cell
- **THEN** the run reports the axis as broken, rather than recording every cell as unscored and rendering an empty-coverage placeholder
