## ADDED Requirements

### Requirement: Selector rot is distinguishable from an empty page

A schema-driven extraction SHALL report a rotted selector distinctly from a page
that legitimately contains nothing.

Where the schema's container selector always matches — a universal element such
as the document body — every failure is reported as EMPTY, and the failure mode
the schema layer exists to detect is exactly the one it cannot report. **The
container selector SHALL therefore be specific enough that its absence is itself
a signal.** A universal container is a forfeit of the distinction, not a
constraint the page imposed: the discriminating selector is usually present and
unlooked-for.

**The two halves are not equally separable, and a requirement that ignores this
cannot be met.** A rotted CONTAINER selector is always distinguishable — its
absence is a fact about the schema. A rotted ITEM selector generally is NOT: for
a page class where "contains nothing" is a legitimate state (an article that
links nowhere, a thread with no replies), zero rows is the same observation
either way, and no verdict can separate them. Requiring a rot verdict there
would be requiring a distinction that does not exist.

Where the item half is inseparable, the extraction SHALL carry a declared
non-zero yield expectation instead — a floor asserted against captured markup —
and that floor SHALL NOT be zeroed, since it is then the only detector. Each
extraction SHALL state which half its verdict covers; a docstring implying
coverage of both is the defect this requirement exists to prevent.

A live network probe SHALL NOT be the only rot detector, for either half: it
makes rot detection depend on the network, which means it is skipped where it is
needed most.

#### Scenario: A universal container is replaced by a discriminating one

- **WHEN** a schema's container selector matches every document
- **THEN** it is replaced by one whose absence signals that the document is not
  the shape the schema was written for, and that absence reports rot

#### Scenario: An inseparable item half declares a yield floor

- **WHEN** zero items is a legitimate state for the page class, so item rot
  cannot produce a verdict
- **THEN** the extraction declares a non-zero yield floor asserted against
  captured markup, and states that its verdict covers the container half only

#### Scenario: Rot is detectable offline

- **WHEN** rot detection runs without network access
- **THEN** a rotted selector is still detectable against captured markup
