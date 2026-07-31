## ADDED Requirements

### Requirement: Selector rot is distinguishable from an empty page

A schema-driven extraction SHALL report a rotted selector distinctly from a page
that legitimately contains nothing.

Where the schema's container selector always matches — a universal element such
as the document body — a rotted item selector produces zero rows and is reported
as EMPTY. The two conditions are then indistinguishable, and the failure mode the
schema layer exists to detect is exactly the one it cannot report.

The container selector SHALL be specific enough that its absence is itself a
signal, or the extraction SHALL report rot by another means. A live network probe
SHALL NOT be the only rot detector: it makes rot detection depend on the network,
which means it is skipped where it is needed most.

#### Scenario: A rotted item selector reports rot, not emptiness

- **WHEN** a schema's item selector no longer matches a page that does contain
  items
- **THEN** the extraction reports rot rather than an empty result

#### Scenario: Rot is detectable offline

- **WHEN** rot detection runs without network access
- **THEN** a rotted selector is still detectable against captured markup
