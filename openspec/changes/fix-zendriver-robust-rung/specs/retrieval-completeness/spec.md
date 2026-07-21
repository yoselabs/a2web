## ADDED Requirements

### Requirement: The robust browser rung is a distinct evasion engine

The `browser_robust` escalation rung SHALL use a browser engine and/or
fingerprint profile genuinely distinct from the fast `browser` rung, so that an
escalation from `browser` to `browser_robust` constitutes a second, independent
retrieval attempt rather than a same-engine retry.

Independence is load-bearing on the corroboration invariants: `classify_terminal`
grants `gone_confirmed` only on agreement across independent tiers, and
`is_confirmed_empty` requires an independent browser render. A robust rung that is
merely a rename of the fast engine SHALL NOT be treated as corroboration.

#### Scenario: Robust rung retries with a distinct engine after the fast rung is walled

- **WHEN** the fast `browser` rung renders a page that a gate classifies as walled
- **AND** the fetch escalates to `browser_robust`
- **THEN** the robust attempt is performed by an engine/fingerprint distinct from
  the fast rung, and its outcome is eligible to count as independent corroboration

### Requirement: A same-engine robust fallback is observable, not silent

When operational constraints force `browser_robust` to resolve to the same engine
as `browser` (e.g. a deliberate deployment workaround, or a regression), the
system SHALL emit an observable signal — a structured log event and a decision-log
field — recording that the two rungs resolved to the same engine.

This makes correlated-witness degradation detectable rather than dependent on
institutional memory, and is the condition under which a same-engine workaround
must be reverted.

#### Scenario: Robust rung falls back to the fast engine

- **WHEN** `browser_robust` resolves to the same engine as the fast `browser` rung
- **THEN** a structured log event is emitted naming both rungs and the shared
  engine, and the fetch's decision log records that the robust rung was not an
  independent witness
