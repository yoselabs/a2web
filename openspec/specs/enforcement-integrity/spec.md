# enforcement-integrity Specification

## Purpose

A stated structural invariant SHALL actually be enforced over its full stated
scope. This capability governs the failure where a guard exists, passes, and is
trusted, while the subject it names sits outside the mechanism that enforces it —
distinct from the vacuity failure (a guard that scans nothing) already covered by
the non-vacuity floors. It covers boundary-rule coverage, the ban on describing
fail-open enforcement as fail-closed, and the accuracy of the agent-facing
architecture map.

## Requirements

### Requirement: A boundary rule covers every subject it names

The module-boundary invariant ("packages may not import from `a2web.<domain>`")
is enforced by a hand-maintained module list. The set of modules that list
names and the set of packages that actually exist SHALL be kept identical in
both directions, by an automated check, so that enforcement cannot silently
stop covering a subject the rule names.

A package that is absent from the list receives no boundary contract at all —
it inherits the permissive parent module and may import domain code freely.
A listed module that no longer exists degrades the boundary tool to a warning
that still exits zero. Both losses are invisible in a passing build, so neither
may be left to review.

#### Scenario: A new package is added without a boundary entry

- **WHEN** a package exists under the packages directory with no corresponding
  entry in the module-boundary configuration
- **THEN** the gate SHALL fail, naming the unlisted package
- **AND** the failure message SHALL state that an unlisted package has no
  boundary contract rather than a passing one

#### Scenario: A retired package is left in the configuration

- **WHEN** the module-boundary configuration names a module that no longer
  exists in the source tree
- **THEN** the gate SHALL fail, naming the stale entry
- **AND** it SHALL NOT be sufficient for the boundary tool to emit a warning
  and exit zero

#### Scenario: The coverage check is itself non-vacuous

- **WHEN** the coverage check runs
- **THEN** it SHALL assert it found a non-zero number of packages and a
  non-zero number of configured modules before comparing them, so that a moved
  directory or an unreadable configuration fails loudly instead of reporting
  two empty sets as consistent

### Requirement: Enforcement that can fail open is not described as fail-closed

An invariant enforced only by a mechanism that silently permits the violation
when unavailable — such as a git hook that resolves its check out of an
external clone and exits zero when that clone is absent — SHALL NOT be
documented as a hard block.

Such an invariant SHALL additionally be enforced by a check that runs inside
the project's own gate, so that a fresh clone and a continuous-integration
runner are protected identically to a fully-configured developer machine.

#### Scenario: A dependency is repointed at a local working copy

- **WHEN** a shared-library dependency in the project manifest resolves to a
  local filesystem path or an editable install rather than a pinned remote
  revision
- **THEN** the gate SHALL fail, naming the dependency and the offending source
- **AND** this SHALL hold on a machine where the external clone providing the
  git hook is absent

#### Scenario: Documentation describes the available protection

- **WHEN** project documentation describes the protection for this invariant
- **THEN** it SHALL name the gate check as the enforcing mechanism
- **AND** it SHALL NOT assert that the git hook alone blocks the violation

### Requirement: The agent-facing architecture map resolves

The primary agent-facing instruction file is the map agents navigate the
codebase by. Every repository path it cites as describing the CURRENT state of
the system SHALL resolve to a file that exists.

A citation may legitimately refer to a path that no longer exists when it is
recording history — where something used to live, or what a promotion renamed.
Such a mention SHALL be distinguishable from a current-state citation, and the
check SHALL provide an explicit way to express it rather than requiring the
sentence to be deleted.

#### Scenario: A cited module is moved or promoted away

- **WHEN** the instruction file cites a repository path as current and that
  path does not exist
- **THEN** the gate SHALL fail, naming the citation and the file that contains
  it
- **AND** the failure message SHALL offer both remedies: correct the path, or
  mark the mention as historical

#### Scenario: A historical mention is preserved

- **WHEN** the instruction file records that a module formerly lived at a path
  that no longer exists, using the documented historical-mention convention
- **THEN** the gate SHALL pass
- **AND** the convention SHALL NOT require rewriting the sentence into prose
  that omits the path, since the path is the informative part of the record

#### Scenario: The citation check is itself non-vacuous

- **WHEN** the citation check runs
- **THEN** it SHALL assert that it extracted at least a floor number of
  citations from the instruction file, so that a change to the file's markup
  fails loudly instead of silently checking nothing

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

### Requirement: A task's cited evidence is verified at the citation before it is acted on

A planning task that cites a `file:line`, a constant, or a shipped behaviour as
its justification SHALL have that citation checked at the cited location before
the task is implemented. Where the citation does not hold, the task SHALL be
closed as disproved with the measurement recorded — never silently reworded into
whatever turned out to be true, and never implemented anyway on the strength of
its general shape.

This is a measured failure rate, not a caution. Across `close-guards-that-read-
green` and `repay-the-shelf-debt`, five tasks were found to cite evidence that
did not hold: two described the *code* that blesses a baseline while the
*baselines* were the stale thing; one cited a constant's declaration line and
read it as the gate, when the gate two hundred lines away had always been
correct; one asserted a capability was undetected offline when a sibling handler
had detected it offline for a month; one requested a distinction that is
logically unavailable under the design it assumed. In each case the task named
the shape of a real problem and got the specifics wrong, because it was authored
from a scan without opening the call site.

The consequence of skipping the check is not a wasted task. It is a change that
implements a defence against a defect that does not exist, leaving the defect
that does — and a delta spec asserting a SHALL the system cannot satisfy.

A delta spec SHALL state what shipped rather than what was hoped. Where
implementation proves a requirement unmeetable as written, the requirement SHALL
be amended before archive; archiving an unmet SHALL converts a known gap into a
false record of enforcement.

#### Scenario: A cited line is checked before the task is implemented

- **WHEN** a task justifies itself by citing a location in the source
- **THEN** that location is read, and a citation that does not hold closes the
  task as disproved with the finding recorded

#### Scenario: A requirement proved unmeetable is amended, not archived

- **WHEN** implementation shows a delta requirement asserts a distinction the
  design cannot provide
- **THEN** the requirement is rewritten to state the separable part and to name
  the inseparable part explicitly, before the change is archived
