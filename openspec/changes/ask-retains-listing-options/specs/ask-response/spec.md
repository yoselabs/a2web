## ADDED Requirements

### Requirement: ask retains the parsed listing options (rank, don't skip)

On a listing-selection question, the `ask` envelope SHALL carry a conditional
`options` list projected from the parsed listing records — one entry per parsed
record, each naming the record's title, url, and its own detail text (carrying
price / rating as extracted). The `answer` MAY still crown a ranked top pick; the
`options` list SHALL preserve the parsed page order and SHALL NOT be re-ranked by
a2web, so a lower-ranked or unrated item (e.g. a premium/niche option) remains
visible rather than deleted. The field SHALL be populated iff the record detector
produced a record set for the page, SHALL be absent from the wire on non-listing
pages (no record set), and SHALL be treated as omit-empty by `_prune_wire`. The
list carries the parsed (fetched) records only and does NOT assert completeness —
the `listing_partial` / `listing_more` signals still own the completeness axis.

#### Scenario: Listing ask carries the option set alongside the ranked answer

- **WHEN** an `ask` fetch returns a listing whose record detector parsed N records
- **THEN** the wire carries `options` as a list of N entries, each with a title, url, and detail
- **AND** `answer` may name a top pick, but every parsed record is present in `options`, in page order

#### Scenario: Options are not re-ranked by a2web

- **WHEN** an `ask` fetch over a price-sorted listing returns an `options` list
- **THEN** the `options` preserve the page order (a2web does not reorder them by rating or price)
- **AND** any ranking is expressed only in `answer`, not by the position of items in `options`

#### Scenario: Non-listing ask omits the field

- **WHEN** an `ask` fetch returns an article or single entity (no record set parsed)
- **THEN** `options` is absent from the wire (not present as `null` or `[]`)

#### Scenario: Empty option set is omitted

- **WHEN** a listing parse yields no usable records
- **THEN** `options` is absent from the wire
