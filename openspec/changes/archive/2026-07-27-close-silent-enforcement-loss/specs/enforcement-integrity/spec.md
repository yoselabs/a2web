## ADDED Requirements

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
