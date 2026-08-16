## MODIFIED Requirements

### Requirement: Closed-enum status, confidence, and cache state

The system SHALL define `FetchStatus` as a closed `StrEnum` (`ok`, `failed`), `Confidence` as `(high, medium, low)`, and `CacheState` as `(hit, miss, bypass)`.

Every member of `FetchStatus` SHALL have at least one producer in `src/`. A member that no code path can emit SHALL NOT be declared: it presents a calling agent with a state it can never receive, and any consumer branching on it holds unreachable code. `status` carries one bit — whether the ladder terminated cleanly; the detail lives in `Verdict`, `TerminalOutcome`, `retrieval_incomplete`, and `operator_hints[].code` (ADR-0019).

#### Scenario: Each enum is closed at construction

- **WHEN** code attempts to construct a `FetchResponse` with an out-of-set status, confidence, or cache value
- **THEN** pydantic raises a validation error

#### Scenario: A declared status with no producer fails the suite

- **WHEN** a member is added to `FetchStatus` and no code path in `src/` assigns or returns it
- **THEN** the architecture guard fails, naming the unproduced member

#### Scenario: A comparison is not a producer

- **WHEN** the only occurrence of a `FetchStatus` member in `src/` is a comparison against it (`status == FetchStatus.<member>`)
- **THEN** the guard still reports the member as unproduced, because a comparison against a value nothing emits is the dead consumer branch the rule exists to prevent
