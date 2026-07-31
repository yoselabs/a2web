## ADDED Requirements

### Requirement: A local fix to a shared primitive is repaid upstream

Where a defect in a shared primitive is diagnosed and a corrected implementation
is written locally, the correction SHALL be offered upstream, and the defect
SHALL be recorded against the shared package whether or not the correction is
accepted.

Rejecting a shared package because it carries a defect is a valid local decision
and only half of one. Every other consumer keeps the defect, and — because the
rejection is recorded as a rejection rather than a bug — none of them learns
that a diagnosis and a fix exist.

Where a repaid fix changes the output of a shared package, existing consumers
SHALL be notified before the change lands. A correction is still a change to a
live surface, and the consumer takes the bump.

#### Scenario: A rejected package is filed against

- **WHEN** a shared package is rejected for adoption because of a defect
- **THEN** the defect is filed against that package, with the local corrected
  implementation cited

#### Scenario: Consumers are told before a corrected output ships

- **WHEN** a repaid fix changes a shared package's output
- **THEN** its known consumers are notified before release

### Requirement: An adopted primitive is not hand-rolled alongside

Where a primitive is a declared dependency, its job SHALL NOT also be implemented
inline. Where a primitive is imported and re-exported but never called, it SHALL
be used or the import removed.

An import plus a parallel hand-rolled implementation is worse than no adoption: a
reader sees the dependency and concludes there is one implementation, so the
divergence between them goes unexamined. Divergence is the observed outcome, not
the hypothetical one — two duration formatters in this codebase already disagree
for every value above a threshold, and one question about emptiness has three
answers in a single file.

Where a shared primitive genuinely does not cover a case, the gap SHALL be
recorded as a gap rather than silently filled by a local implementation sitting
next to the import.

#### Scenario: An unused adopted primitive is used or dropped

- **WHEN** a shared primitive is imported and called from nowhere
- **THEN** it is either adopted at the sites doing its job, or the import is
  removed

#### Scenario: A genuine gap is recorded

- **WHEN** a shared primitive does not cover a required case
- **THEN** the gap is recorded against the shared package, and the local
  implementation cites it

### Requirement: A ban on hand-rolled substrate is scoped to every module that could violate it

Where a rule bans a hand-rolled implementation in favour of a shared primitive,
the rule's scope SHALL cover every module capable of violating it.

A ban scoped to one directory, while a sibling directory does the banned thing
freely, reads as a project-wide rule and enforces a local one. Both the rule's
text and any mechanical check SHALL name the full scope.

#### Scenario: The scope covers the violating module

- **WHEN** a module outside a ban's stated scope performs the banned
  construction
- **THEN** the ban's scope is widened to include it, or the exception is recorded
  with its reason
