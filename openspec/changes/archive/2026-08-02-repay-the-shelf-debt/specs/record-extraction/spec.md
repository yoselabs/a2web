## ADDED Requirements

### Requirement: The shipped detector matches the normative selector set

The record detector's heading selector set SHALL match the set this project's
specification declares as normative. Where detection is delegated to a shared
package, the delegation SHALL be verified against the normative set rather than
assumed.

A shipped detector narrower than its spec fails silently and expensively: records
are not detected, the record count stays unset, and both the withheld-body index
and the completeness signal disappear together with no diagnostic. Nothing in the
response distinguishes "this page has no records" from "the detector could not
see them".

Where the shipped behaviour and the normative text disagree, one of them is wrong
and a reader is being misled by whichever they consulted. The disagreement SHALL
be resolved rather than recorded.

#### Scenario: A page using accessible heading roles is detected

- **WHEN** a listing marks its item titles with an accessible heading role rather
  than a heading element
- **THEN** its records are detected

#### Scenario: Delegated detection is verified against the spec

- **WHEN** record detection is delegated to a shared package
- **THEN** a test asserts the delegated selector set matches the normative one
