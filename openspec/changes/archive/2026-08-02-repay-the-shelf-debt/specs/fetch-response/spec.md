## ADDED Requirements

### Requirement: An unavailable resource is not reported as a defect

A failure caused by an unconfigured or unavailable resource — a missing
credential, a disabled provider, an absent optional dependency — SHALL be
reported with a kind that distinguishes it from an internal defect.

Where a typed error taxonomy is adopted but no failure is raised into it, the
taxonomy's dispatch branch is dead and every failure falls through to the
catch-all. A missing credential and a null dereference then render identically as
an internal error. The operator whose configuration is incomplete is told the
software is broken, and cannot act on the message.

A taxonomy's declared kinds SHALL be reachable. A label that no code path can
produce is documentation of an intent, not a behaviour.

#### Scenario: A missing credential reports as unavailable

- **WHEN** a tool fails because a required credential is unconfigured
- **THEN** the error envelope reports an unavailable-resource kind, not an
  internal defect

#### Scenario: Declared kinds are reachable

- **WHEN** the error taxonomy declares a set of kinds
- **THEN** each kind is produced by at least one code path

### Requirement: Emptiness has one definition

The predicate deciding whether a field is empty for wire purposes SHALL have one
implementation.

Several omit-empty implementations in one module — an inline predicate, an
inherited base-class predicate, and an unused adopted helper — are three answers
to one question that nothing compares. Whether a field reaches the caller then
depends on which path serialized it.

#### Scenario: One predicate decides omission

- **WHEN** a field is considered for omission from the wire
- **THEN** a single predicate decides it, regardless of the serialization path
