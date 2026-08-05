## ADDED Requirements

### Requirement: The personal-identifier scan covers every distributed text artifact, including generated exports

The personal-identifier scan SHALL cover every text-ish artifact the shipping
tree distributes, including a generated export of another system's data (such
as the issue-queue's plaintext export), not only hand-authored file suffixes.
A migration that moves personal-identifier-bearing prose out of a scanned
file format and into an unscanned generated export SHALL NOT cause the scan
to read as unchanged while covering less.

#### Scenario: A generated queue export is committed to the shipping tree

- **WHEN** a generated, plaintext export of the issue queue is added to the
  set of files git tracks
- **THEN** the personal-identifier scan SHALL include that export's file
  suffix in its scanned set
- **AND** the existing denylist SHALL apply to it identically to any other
  scanned file

#### Scenario: The widened scan is verified red before green

- **WHEN** the scan's scope is widened to cover a new file suffix
- **THEN** the widening SHALL be run against the repository before any
  content fix, so a failure at that point is the evidence the widened match
  actually works
