## ADDED Requirements

### Requirement: A test MAY name what it protects, using an identifier that already exists

A test MAY declare the artifact it exists to protect via a `protects` marker. The
marker SHALL carry only identifiers that already exist elsewhere in the repository —
a requirement heading in `openspec/specs/`, an ADR id in `docs/adr/`, or a change id
in `openspec/changes/`. No new vocabulary SHALL be invented for this purpose.

Declaration SHALL be OPTIONAL in this change. A mandatory marker would fail 1,534
existing tests on the first run and teach nothing; the obligation is introduced by
the floor requirement below, which constrains the direction of travel rather than the
current position.

The marker SHALL be decidable at write time from information the author already
holds. Choosing it SHALL NOT require reading other tests.

#### Scenario: A test names a spec requirement

- **WHEN** a test declares `@pytest.mark.protects("spec:ask-response", "Requirement: <heading>")`
- **THEN** the suite accepts it, and the reconciliation report counts that requirement
  as traceable

#### Scenario: A test names an ADR

- **WHEN** a test declares `@pytest.mark.protects("adr:0009")`
- **THEN** the suite accepts it, and the report counts ADR-0009 as cited

#### Scenario: A test names an incident rather than a requirement

- **WHEN** a test exists because of a specific past defect and declares
  `@pytest.mark.protects("change:2026-08-01-fix-cache-ttl")`
- **THEN** the suite accepts it, and the report classifies it as a regression witness
  rather than as evidence for any requirement

#### Scenario: An undeclared test is not an error

- **WHEN** a test carries no `protects` marker
- **THEN** the suite passes, and the test is counted in the untraceable baseline

### Requirement: A named identifier SHALL resolve

A `protects` marker naming an artifact that does not exist is worse than no marker: it
reads as a decision while providing none. Every identifier a marker names SHALL
resolve to a real artifact.

The check SHALL carry a non-vacuity floor: it SHALL assert it discovered at least a
stated minimum number of markers and SHALL fail when it discovers none. A check
reporting "0 violations in 0 candidates" is indistinguishable from a passing one.

Requirement headings SHALL be matched against the heading text as it appears in
`openspec/specs/<capability>/spec.md`, whitespace-insensitively, so that reformatting
a spec does not break a citation while renaming a requirement does.

#### Scenario: A marker names a requirement that does not exist

- **WHEN** a test declares a requirement heading absent from the named capability's spec
- **THEN** the architecture suite fails, naming the test and the unresolved heading

#### Scenario: A marker names an ADR that does not exist

- **WHEN** a test declares `adr:0042` and `docs/adr/` holds no such ADR
- **THEN** the architecture suite fails, naming the test and the unresolved id

#### Scenario: A requirement is renamed out from under a citation

- **WHEN** a spec requirement heading is renamed and a test still cites the old text
- **THEN** the architecture suite fails, so the rename surfaces the tests that
  described the old behavior

#### Scenario: The check refuses to pass vacuously

- **WHEN** the marker discovery walk finds no markers at all
- **THEN** the check fails rather than reporting success

### Requirement: Traceability is a monotone floor

The count of requirements traceable to at least one test SHALL be recorded as a floor
and SHALL NOT decrease. New work SHALL NOT dilute traceability; existing tests SHALL
NOT be backfilled to satisfy it.

The floor SHALL be stored as a literal committed value, not derived at run time from
the suite it constrains — a floor computed from current state can only ever report
that the current state equals itself.

Raising the floor SHALL be an ordinary edit accompanying the change that earned it.
Lowering it SHALL require a stated reason recorded alongside the value, because the
only legitimate reason to lower it is that a requirement was deliberately removed.

#### Scenario: A change adds a traceable test

- **WHEN** a change adds the first test citing a previously uncited requirement
- **THEN** the traceable count rises, and the change may raise the recorded floor to match

#### Scenario: A change removes the last citation of a requirement

- **WHEN** the only test citing a requirement is deleted or its marker removed
- **THEN** the floor check fails, because traceability regressed

#### Scenario: A requirement is deliberately retired

- **WHEN** a change removes a requirement from a spec and its citing tests with it
- **THEN** the floor may be lowered in that same change, with the reason recorded
  next to the value

### Requirement: The reconciliation report SHALL distinguish unlocatable from untested

The report SHALL NOT present absence of a capability-named test directory as absence
of tests. Measured 2026-08-05, `proxy-pool` has no capability-named directory and is
nonetheless fully tested under `tier_pipeline`.

Where the report cannot distinguish the two, it SHALL say so in its own output rather
than leaving a reader to infer the stronger claim. Reporting an ambiguity as a finding
is the same class of defect as reporting a miss as a complete answer.

#### Scenario: A capability is tested under another name

- **WHEN** a capability's requirements are exercised by tests filed under a different
  directory
- **THEN** the report lists the capability as lacking *locatable* evidence, and states
  that this does not mean untested

#### Scenario: The report is read as coverage

- **WHEN** the report is emitted
- **THEN** its own output carries the caveat, so the distinction survives being quoted
  out of context
