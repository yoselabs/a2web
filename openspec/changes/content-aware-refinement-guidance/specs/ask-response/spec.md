## ADDED Requirements

### Requirement: Ask envelope carries dimensional refinement axes on a partial listing

The `AskResponse` envelope SHALL carry a conditional `refinement_axes` field on a partial listing,
listing the dimensions to re-query on (per the `refinement-guidance` capability). Each axis SHALL
name a dimension and how to apply it, and SHALL NOT be a specific item value drawn from the biased
sample. The field SHALL be treated as omit-empty by `_prune_wire` — absent from the wire when there
are no axes (a complete listing, or a non-listing page). The field is additive and conditional; it
does not change existing required or debug fields, and it does not alter the tool signature.

#### Scenario: Partial listing surfaces refinement axes

- **WHEN** an `ask` fetch returns a partial listing and the extractor produced refinement axes
- **THEN** the wire payload includes `refinement_axes` as a list of dimensional axes, each naming a dimension and how to apply it

#### Scenario: Complete or non-listing response omits the field

- **WHEN** an `ask` fetch returns a complete listing or a non-listing page (no axes produced)
- **THEN** `refinement_axes` is absent from the wire (not present as `null` or `[]`)

#### Scenario: Axes carry no sample-derived values

- **WHEN** refinement axes are emitted for a price-sorted, truncated listing
- **THEN** each axis names a dimension (e.g. "narrow by brand", "add a price floor") and none recommends a specific item or value taken from the retrieved sample
