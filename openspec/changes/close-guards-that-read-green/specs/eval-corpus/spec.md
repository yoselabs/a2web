## ADDED Requirements

### Requirement: a criterion is addressed to a reader that can read it

Every corpus criterion SHALL be readable by at least one scoring path. A
criterion naming a field no axis is given, or a property no axis can observe, is
decorative — it reads as coverage while contributing nothing to the score.

A criterion asserting the absence of fabrication requires ground truth. The judge
SHALL therefore be given the fetched page when scoring answer quality, or such
criteria SHALL be reformulated as deterministic assertions over the envelope.

Where a deterministic assertion vocabulary already exists for offline replay, the
live bench SHALL use the same vocabulary per cell rather than leaving the same
properties unchecked.

#### Scenario: A criterion naming an unobservable property is rejected

- **WHEN** a corpus criterion names an envelope field no axis reads
- **THEN** the criterion is either wired to an axis that reads it or removed

#### Scenario: The quality judge can verify against the source

- **WHEN** an answer is scored for fabrication
- **THEN** the judge is given the fetched page content

### Requirement: every first-class invariant has at least one catching cell

Each first-class product invariant SHALL have at least one corpus cell whose
failure is caused by violating that invariant, and the mapping from invariant to
catching cell SHALL be recorded.

An invariant witnessed nowhere is enforced only by the code that implements it,
and a change to that code is unopposed. An invariant witnessed only where it has
no code implementer is witnessed exactly where it is not enforced — the two
halves must not be inverted.

The wire half of an invariant SHALL be witnessed as well as the attribute half.
Assertions reading response attributes do not exercise the wire projection, which
is the layer agents consume.

#### Scenario: An invariant with no catching cell is recorded as a gap

- **WHEN** the invariant-to-cell mapping is produced
- **THEN** every invariant with zero catching cells is listed as an open gap

#### Scenario: The observed projection carries the completeness signals

- **WHEN** a replay case observes a failed retrieval
- **THEN** the observation includes the incompleteness flag and the narrative, so
  a regression on either is catchable
