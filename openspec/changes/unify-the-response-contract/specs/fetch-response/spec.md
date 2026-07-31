## ADDED Requirements

### Requirement: The operator-hint code set is a declared closed vocabulary

Every operator hint code SHALL be a member of one declared vocabulary. Every hint
SHALL be constructed through a factory belonging to that vocabulary; a hint code
SHALL NOT exist only as an inline string literal at a construction site.

Any code that dispatches on a hint code SHALL compare against the declared
vocabulary, never against a string literal.

A set of codes that is matched on by string but declared nowhere is a closed enum
without a compiler. A typo produces a branch that never fires and a test that
cannot notice.

#### Scenario: A hint is constructed through the vocabulary

- **WHEN** an operator hint is constructed anywhere in the pipeline
- **THEN** its code is a member of the declared vocabulary

#### Scenario: Dispatch compares against the vocabulary

- **WHEN** code branches on a hint code
- **THEN** it compares against the declared member, not a string literal

### Requirement: A field decided once is not re-derived downstream

Where a decision is recorded as a field on the fetch context, downstream
projection SHALL read that field. It SHALL NOT recompute the same decision from
the presence or absence of a hint, a message, or any other rendering.

Where a value is genuinely decided in two phases, the phases SHALL be separately
named, so that a single field name does not mean one thing to one tool's callers
and another to a second tool's callers.

#### Scenario: The projection reads the recorded decision

- **WHEN** the projection needs a promotion decision that the pipeline already
  recorded
- **THEN** it reads the recorded field rather than re-deriving it from hints

#### Scenario: A two-phase value names its phases

- **WHEN** a field's value is refined after an initial decision
- **THEN** the initial and final values are distinguishable by name, and each
  tool's callers can tell which they received

### Requirement: The TSV field set has one declaration and an equality guard

The set of envelope fields rendered as TSV SHALL be declared literally in exactly
one place. Both the model-side serializer and the wire-side encoder SHALL consume
that declaration, and a guard SHALL assert the two halves describe the same set.

The literal table exists because inference is how a newly added field silently
changes the agent-facing wire. Two literal tables in two modules reintroduce the
same hazard through duplication instead of introspection: nothing asserts they
agree, and a field can be TSV on one path and absent on the other.

Where the column decision requires typed rows before serialization, that decision
MAY remain model-side; the declaration of *which fields are TSV* SHALL still be
single. A field that neither half encodes SHALL be recorded in the declaration as
not-TSV rather than left undecided.

The TSV codec SHALL have one in-tree consumer.

#### Scenario: Adding a TSV field requires one edit

- **WHEN** a field is added to the TSV set
- **THEN** it is declared once and both encoding paths honour it

#### Scenario: Divergent halves fail the guard

- **WHEN** the model-side and wire-side TSV sets differ
- **THEN** the guard fails
