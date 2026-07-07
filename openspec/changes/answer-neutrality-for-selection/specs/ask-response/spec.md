## ADDED Requirements

### Requirement: ask is neutral on selection questions

The `ask` answer SHALL NOT assert a2web's own unqualified "best" on a question
that asks a2web to pick from a set (a which/best/compare question over a listing
or option set). It MAY offer a criterion-disclosed lead (naming the criterion and
framing it as one lens, e.g. "by rating, X leads"), and it SHALL relay any
source-stated preference attributed to the page (e.g. "the site marks X as
preferred"), never as a2web's own judgment. The answer SHALL present the option
space rather than decide it, and SHALL remain exhaustive (it MUST NOT decline and
under-deliver in the same breath). Single-fact questions (e.g. asking for a phone
number) are out of scope and answer as before.

#### Scenario: Selection question offers a criterion-disclosed lead, not a verdict

- **WHEN** an `ask` fetch answers a "which is best?" question over a listing
- **THEN** the answer does not assert an unqualified "best"
- **AND** any lead it offers names the criterion and frames it as one lens, not the answer

#### Scenario: Source-stated preference is relayed, attributed

- **WHEN** the fetched page marks its own preference (e.g. a contact page tags one channel "preferred")
- **THEN** the answer surfaces that preference as the source's ("the site marks X as preferred")
- **AND** the answer does not present it as a2web's own recommendation

#### Scenario: Neutral is not lazy

- **WHEN** the answer declines to crown a single best
- **THEN** it still presents the option space (and relays source preference / criteria) in the same response
- **AND** does not force the caller to re-ask the same page to recover data already on it

#### Scenario: Single-fact question is unaffected

- **WHEN** an `ask` fetch answers a single-fact question (not a selection over a set)
- **THEN** the answer behaviour is unchanged (lean, direct)

### Requirement: criteria surface on any listing selection, not only partial ones

`refinement_axes` (the judgable dimensions of the option set) SHALL be surfaced on
any listing selection question, decoupled from the completeness signal — not gated
on the listing being partial. Criteria and partialness are orthogonal: a complete
listing still needs its criteria surfaced for a "best?" question. The field remains
additive and omit-empty (absent when there are no axes or the page is not a listing).

#### Scenario: Complete listing still surfaces criteria

- **WHEN** an `ask` fetch returns a complete listing (no `listing_partial` signal) for a selection question
- **THEN** `refinement_axes` may still be present (gated on the listing kind, not on partialness)

#### Scenario: Non-listing omits criteria

- **WHEN** an `ask` fetch returns a non-listing page
- **THEN** `refinement_axes` is absent from the wire
