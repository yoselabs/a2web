## ADDED Requirements

### Requirement: a criterion is addressed to a reader that can read it

Every corpus criterion SHALL be readable by at least one scoring path, or SHALL
be recorded as unreadable. A criterion naming a field no axis is given, or a
property no axis can observe, contributes nothing to the score — and an
unreadable criterion left unrecorded reads as coverage while providing none.

A criterion asserting the absence of fabrication requires ground truth. Such
criteria SHALL be reformulated as deterministic assertions over the envelope
where the property admits one; where it does not, they SHALL appear in the
invariant-to-cell mapping as an open gap rather than be deleted. Deleting them
would satisfy the letter of this requirement while erasing the record of what is
unguarded.

Where a deterministic assertion vocabulary already exists for offline replay, the
live bench SHALL use the same vocabulary per cell rather than leaving the same
properties unchecked. A key one harness cannot evaluate SHALL be reported as
unobservable, never as a pass.

#### Scenario: A criterion naming an unobservable property is rejected

- **WHEN** a corpus criterion names an envelope field no axis reads
- **THEN** the criterion is wired to an axis that reads it, converted to a
  deterministic assertion, removed, or recorded as an open gap

#### Scenario: A URL claim is checked without a judge

- **WHEN** an answer cites a URL
- **THEN** it is asserted to appear in the retrieved body, the emitted index, or
  the page's own address, deterministically and with no model in the loop

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
