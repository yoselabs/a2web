# fetch-response

## ADDED Requirements

### Requirement: A gated section blocking the answer caps confidence and is flagged

When a page section that the caller's question targets was withheld behind an
in-page interaction a2web cannot perform, `confidence` SHALL NOT be `high` — a
`high` computed confidence SHALL be capped to `medium` — and `operator_hints`
SHALL include an `interaction_required` hint. The cap SHALL only ever lower
confidence, never raise it.

`confidence` SHALL NOT be capped to `low` for this condition. `low` is reserved
for a non-ok verdict, an extractor-reported page-level obstacle, or an absent
answer — all states in which retrying by another route is the correct next
action. A gated section is the opposite case: the page was retrieved, the answer
is a reliable report of a gap, and no retry recovers it.

`retrieval_incomplete` SHALL NOT be set for this condition. It remains scoped to
a requested URL that was not retrieved; here the URL was retrieved and its
primary content is intact.

A gated section that does not block the caller's question SHALL NOT trigger the
cap or the hint.

#### Scenario: A blocking gate caps high confidence

- **WHEN** `query` completes on a page whose gated section the question targets, with a computed confidence of `high`
- **THEN** the envelope's `confidence` is `medium` and `operator_hints` includes an `interaction_required` entry

#### Scenario: The cap never raises confidence

- **WHEN** a blocking gate is detected on a fetch whose computed confidence is already `medium` or `low`
- **THEN** `confidence` stays at that computed value — the cap only ever lowers `high`

#### Scenario: A blocking gate does not fail the fetch

- **WHEN** a blocking gate is detected on an otherwise successful fetch
- **THEN** `retrieval_incomplete` is absent from the wire payload
- **AND** `status` is unchanged by the gate

#### Scenario: A non-blocking gate leaves confidence untouched

- **GIVEN** a page carrying a gated section irrelevant to the question asked
- **WHEN** the retrieved body fully answers the question
- **THEN** `confidence` is unaffected and no `interaction_required` hint is present

### Requirement: `confidence` and the hint branching surface SHALL be declared to callers

`confidence` SHALL be documented as grading **retrieval quality** — how much of
what a2web attempted to retrieve it obtained, and from where — and SHALL NOT be
documented or described as a measure of how much the answer's content can be
trusted. The declaration SHALL appear both on the `Confidence` type and in the
`query` tool description a calling agent reads.

`operator_hints[].code` SHALL be documented in the `query` tool description as
the stable identifier agents branch on for a next action.

#### Scenario: A caller can read what confidence means

- **WHEN** a calling agent reads the `query` tool description
- **THEN** it states that `confidence` grades retrieval quality rather than answer trustworthiness
- **AND** it states that `operator_hints[].code` is the stable identifier to branch on
