## ADDED Requirements

### Requirement: Deferred work is tracked as beads, not a flat file

Deferred and open work items SHALL be tracked as `bd` issues in the repo's
embedded Dolt database, not as entries in a flat markdown file. `BACKLOG.md`
and `BACKLOG-CLOSED.md` SHALL NOT exist in the repository once this
requirement is satisfied.

#### Scenario: A new deferral is recorded

- **WHEN** an OpenSpec change's proposal carries an "Out of Scope" or
  "Non-Goals" deferral
- **THEN** the deferred item SHALL be recorded as a `bd create` issue, not
  appended to a markdown file

#### Scenario: The flat files are gone

- **WHEN** the repository is inspected after this change lands
- **THEN** neither `BACKLOG.md` nor `BACKLOG-CLOSED.md` SHALL be present

### Requirement: A parked item's wait state is modeled by the mechanism that matches its cause

A deferred or on-hold item's stored state SHALL reflect *why* it is not
ready, using three distinct mechanisms rather than one:

- Waiting on another tracked issue SHALL be modeled as a real `blocks`
  dependency onto that issue, so the item automatically becomes ready when
  the blocking issue closes.
- Deliberately shelved work with no specific blocker SHALL use the native
  `deferred` status.
- Waiting on something with no bead of its own (an external access request,
  a pending human decision) SHALL use the manual `blocked` status, and the
  reason SHALL be recorded on the issue (via a comment or notes update).

A synthetic blocking dependency created only to represent "not blocked by
anything specific, just not started yet" SHALL NOT be used — that case SHALL
use `deferred`.

#### Scenario: An item waits on another tracked issue

- **WHEN** a deferred item's completion genuinely depends on another tracked
  issue closing
- **THEN** a `blocks` dependency SHALL link the two issues
- **AND** the dependent issue SHALL NOT appear in `bd ready` until the
  blocking issue closes

#### Scenario: An item is shelved with no specific blocker

- **WHEN** an item is deliberately set aside for later reconsideration, with
  nothing specific preventing it from being worked
- **THEN** the item SHALL be set to `deferred` status with a recorded reason
- **AND** it SHALL NOT be linked via a dependency to an issue invented solely
  to serve as its blocker

### Requirement: A bead that resolves an OpenSpec change is linked to it

A bead whose resolution is tied to a specific OpenSpec change SHALL record
that link using the issue's specification-link field, pointing at the
change's proposal document, not as free text inside the description.

#### Scenario: A bead is created for an item surfaced by a change

- **WHEN** a bead is created for work surfaced by an OpenSpec change's
  findings or deferrals
- **THEN** the bead's specification-link field SHALL be set to that change's
  proposal path

### Requirement: Narrative and evidence content is not represented as a work item

Content with no lifecycle — a retrospective, a retraction, a measurement
writeup, a dependency-graph explanation covering multiple issues — SHALL NOT
be created as a bead. Such content SHALL be recorded as a document under
`docs/findings/`. A bead that references such content SHALL point to it
rather than duplicate or absorb it.

#### Scenario: A retrospective essay is migrated

- **WHEN** a `BACKLOG.md` block contains reasoning or a retraction with no
  status, assignee, or completion criterion
- **THEN** it SHALL be moved to a `docs/findings/` document
- **AND** no bead SHALL be created to represent it

#### Scenario: A trackable item cites long-form evidence

- **WHEN** a bead's justification is longer than a short paragraph
- **THEN** the bead SHALL carry a pointer to the `docs/findings/` document
  holding the evidence, rather than the evidence itself

### Requirement: The generated queue export stays current across queue-only sessions

The committed plaintext export of the issue queue SHALL be refreshed before
any push, including a push whose session made no source-code changes.

#### Scenario: A session only updates the issue queue

- **WHEN** a session claims, comments on, or closes issues but changes no
  source files
- **THEN** the exported queue file SHALL still be refreshed before that
  session's changes are pushed
