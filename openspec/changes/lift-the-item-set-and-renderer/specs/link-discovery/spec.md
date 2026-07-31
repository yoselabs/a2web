## ADDED Requirements

### Requirement: The link cap has one declaration

The cap on emitted onward links SHALL be declared once and read by every site
that applies it. A cap stated as an invariant in the specification and
implemented as several hardcoded literals cannot be changed where it is stated,
and drifts silently at the sites that hold it.

A health baseline — a probe expectation, a golden, a recorded observation — SHALL
NOT record a value that violates the declared cap as healthy. Such a baseline
pins the violation green and converts the correction into an apparent regression.

#### Scenario: The cap changes in one place

- **WHEN** the onward-link cap is changed
- **THEN** every emitting site honours the new value without a further edit

#### Scenario: A baseline does not certify a violation

- **WHEN** a probe baseline records an observed link count
- **THEN** that count is within the declared cap

### Requirement: A truncated set declares its truncation

Where a set of items or links is capped, the response SHALL declare that
truncation and, where the total is known, the total.

The withheld-body index exists so a caller that never sees the body knows what it
did not receive. An index that is itself silently truncated tells the caller the
list is the list. That is the same harm as a silent miss, arriving through the
index rather than through the body.

Where the producing source reports a total — an API result count, a listing
header — that total SHALL be carried rather than discarded, and the
post-truncation count alone SHALL NOT be presented as the count.

#### Scenario: A capped listing reports its shortfall

- **WHEN** a listing's items exceed the cap
- **THEN** the response declares the truncation and the total where known

#### Scenario: A known total is not discarded

- **WHEN** the source reports a total item count
- **THEN** that total reaches the caller rather than being replaced by the capped
  count
