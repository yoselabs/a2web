## MODIFIED Requirements

### Requirement: ask retains the parsed listing options (rank, don't skip)

On a listing-selection question, the `ask` envelope SHALL carry a conditional
`options` list projected from the parsed listing records — one entry per parsed
record, each naming the record's title, url, and its own detail text (carrying
whatever did not fit a typed field, as extracted). When the record was parsed
from the page's own JSON-LD or framework-state listing declaration, the entry
SHALL additionally carry independently-optional typed fields — `price`,
`currency`, `rating`, `stock`, `seller` — read verbatim from that declaration;
a field SHALL be omitted (not fabricated, not backfilled from another fetch)
when the source declaration does not carry it at the listing level. Entries
whose record came from the generic structural (DOM) record detector instead
SHALL carry no typed fields — `detail` remains their only representation,
unchanged from prior behavior. The `answer` MAY still crown a ranked top pick;
the `options` list SHALL preserve the parsed page order and SHALL NOT be
re-ranked by a2web, so a lower-ranked or unrated item (e.g. a premium/niche
option) remains visible rather than deleted. The field SHALL be populated iff
the record detector produced a record set for the page, SHALL be absent from
the wire on non-listing pages (no record set), and SHALL be treated as
omit-empty by `_prune_wire`. The list carries the parsed (fetched) records
only and does NOT assert completeness — the `listing_partial` / `listing_more`
signals still own the completeness axis.

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

#### Scenario: JSON-LD-sourced option carries typed commerce fields

- **WHEN** an `ask` fetch returns a listing whose options were parsed from the
  page's JSON-LD `ItemList` (the DOM record detector produced nothing on this
  page)
- **THEN** each option whose source row carried `offers.price` /
  `offers.priceCurrency` / `aggregateRating.ratingValue` carries them as
  typed `price`, `currency`, `rating` fields, independent of `detail`

#### Scenario: Field absent from the source is omitted, not guessed

- **WHEN** a JSON-LD-sourced option's source row has no `offers.availability`
  or no `offers.seller`
- **THEN** the option's `stock` / `seller` field is absent from the wire —
  a2web does not fetch the item's own page to fill it, and does not report a
  value the listing declaration did not state

#### Scenario: DOM-mined option carries no typed fields

- **WHEN** an `ask` fetch returns a listing whose options were parsed from the
  generic structural (DOM) record detector (with or without JSON-LD also
  present on the page — the DOM detector's result takes precedence per
  existing behavior)
- **THEN** every option in the list has `price`, `currency`, `rating`,
  `stock`, and `seller` absent from the wire
- **AND** `detail` is unchanged from prior (pre-typed-fields) behavior
