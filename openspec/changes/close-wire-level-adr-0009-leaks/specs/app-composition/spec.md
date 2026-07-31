## ADDED Requirements

### Requirement: Operator faults reach the wire as typed errors, not defects

An error whose cause is configuration, credentials, or an unavailable declared
resource SHALL be raised as the corresponding `a2effect` `AppError` subclass, so
that `guard_tool`'s typed branch renders it as that class. It SHALL NOT reach
the wire as `UnexpectedDefect`.

`UnexpectedDefect` means "a2web has a bug". A missing LLM key means "the
operator has not finished configuring a2web". Rendering both identically tells
the caller to file a bug report for something only the operator can fix, and
tells the operator nothing.

The typed branch is presently unreachable: a2web imports `a2effect` in exactly
one module and raises none of its five error types, so every tool failure is
quarantined. The taxonomy is adopted at the boundary and unused behind it.

#### Scenario: A missing provider key is an operator fault

- **WHEN** a tool fails because no LLM provider is configured
- **THEN** the error envelope names the typed operator/configuration class, not
  `UnexpectedDefect`

#### Scenario: A genuine bug is still a defect

- **WHEN** a tool body raises an error that is not an `AppError`
- **THEN** it is quarantined into `UnexpectedDefect` and the envelope says so

#### Scenario: The typed branch is exercised

- **WHEN** the test suite runs
- **THEN** at least one test drives a tool failure through the `except AppError`
  branch, so the branch cannot silently become unreachable again
