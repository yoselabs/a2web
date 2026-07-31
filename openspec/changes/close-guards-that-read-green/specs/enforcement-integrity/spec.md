## ADDED Requirements

### Requirement: A guard is named and cited for the invariant it asserts

A test's name, its docstring, and every document citing it SHALL describe the
invariant it actually asserts. One test SHALL NOT stand as the enforcement of two
unrelated invariants because a word in its name applies to both.

A guard whose population is empty SHALL be removed and its absence recorded,
rather than retained as a passing check. A guard over zero candidates is
indistinguishable from a passing one — the same pathology the anti-vacuity rule
addresses, arriving through the population rather than the walk.

#### Scenario: A conflated guard is renamed or split

- **WHEN** a test asserts one invariant while documentation cites it for another
- **THEN** the test is renamed to its real invariant, and the other citation is
  either backed by a real test or withdrawn

#### Scenario: A guard with no candidates is retired

- **WHEN** a guard's population is empty across the whole repository
- **THEN** the guard is removed and the absence of that check is recorded

### Requirement: A cited rule resolves to a test function that exists

Every architecture rule cited in `CLAUDE.md`, `docs/architecture/README.md`, or
`docs/architecture/verification-provenance.md` SHALL resolve to a test file
**and**, where a function is named, to that function. Resolution SHALL be
mechanically checked, and the check SHALL cover directory citations and
`path::function` citations, not file paths alone.

A dead citation is worse than a missing guard: a reader concludes the invariant
is enforced and stops looking. Where a verification-budget recommendation reasons
from a guard's existence, a dead citation makes the recommendation unsound.

#### Scenario: A citation naming a nonexistent test fails

- **WHEN** documentation cites an architecture test that does not exist
- **THEN** the citation-resolution guard fails

#### Scenario: A citation naming a missing function fails

- **WHEN** documentation cites `path::function` and the file exists but the
  function does not
- **THEN** the citation-resolution guard fails

### Requirement: A declared verification dependency is used or removed

A dependency declared for verification purposes SHALL be imported by at least one
test, or SHALL be removed from the project.

A declared-but-unused verification library reads to an auditor as capability. If
the loop it was meant to close is still open, the open loop SHALL be recorded as
open rather than represented by an installed package.

#### Scenario: An unused verification dependency is dropped

- **WHEN** a verification library is declared and imported by no test
- **THEN** it is removed and any documentation promising its future use is
  corrected to state the gap

### Requirement: A correctness claim is not enforced only by a re-blessable golden

A wire-level correctness claim — a required field, a required severity — SHALL be
asserted by a test that reads the wire directly, independent of any golden
byte-comparison.

A golden proves a surface has not changed; it does not prove the surface was
right when captured, and it is re-blessable. An ADR-0009 signal whose only
enforcement is a byte-compare can be downgraded — the never-silently-miss klaxon
turned into an informational note — by one re-bless.

A bless operation SHALL validate its target against the known set, so a typo or
an omitted argument cannot rewrite every golden in one run.

#### Scenario: Downgrading a critical hint fails a non-golden test

- **WHEN** a failed-retrieval envelope's critical operator hint is downgraded in
  the wire projection
- **THEN** a capability test reading the wire fails, independently of any golden

#### Scenario: Blessing validates its target

- **WHEN** a bless operation is invoked with an unrecognised target
- **THEN** it fails rather than rewriting every golden
