## ADDED Requirements

### Requirement: The withheld-body index does not depend on how the item set was found

Where a page presents a set of items, the affordances derived from that set — the
onward pointers and the same-page option index — SHALL be derived regardless of
which extraction path produced the set.

A page whose items are mined from the DOM and the same page whose items are read
from embedded structured data present the same content to the caller. Deriving
the index on one path and not the other means the caller's ability to find what
was withheld depends on an implementation detail of extraction, which the caller
cannot see and did not choose.

The derivation SHALL have one implementation over one representation of the item
set, so that a source added later inherits the affordances rather than
re-implementing them.

#### Scenario: A structured-data listing ships the same index as a mined one

- **WHEN** a listing page's items are read from embedded structured data
- **THEN** the onward pointers and option index are derived as they are for a
  DOM-mined listing

#### Scenario: A new item source inherits the derivation

- **WHEN** a new extraction path produces an item set
- **THEN** it produces the same affordances without a new derivation
  implementation
