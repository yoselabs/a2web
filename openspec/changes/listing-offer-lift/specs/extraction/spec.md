## MODIFIED Requirements

### Requirement: JSON-LD ItemList synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `ItemList` payload — an `itemListElement` array of `ListItem` entries — into record rows. For each list item the adapter SHALL lift commerce fields out of nested objects before rendering: `offers.price` combined with `offers.priceCurrency` into a single price token (e.g. `3690 TRY`), `offers.url` into the row url, and `aggregateRating.ratingValue` into a rating. A row's top-level scalar `price`/`url` (flat-shaped payloads) SHALL pass through unchanged. `json_in_script` already detects `ld_json` payloads and `rank_payloads` already prefers `ItemList`; this requirement closes the synthesis gap so a detected `ItemList` becomes usable `content_md`.

Commerce-shaped lists — rows where at least half carry a lifted `price` or `url` — SHALL render as linked markdown records, one per item: `- [<name>](<url>) — <price> ⭐ <rating>`, with `price` and `rating` omitted when absent and a plain name used when no url is present. The product url SHALL appear verbatim and un-truncated (the linked-record form is not subject to the fixed-width table's per-cell character cap), so downstream router-shape extraction can cite it as a `try_url` drilldown. The synthetic `image` field SHALL NOT be emitted for listing rows. Link text SHALL be sanitized so item names containing `]`, `)`, or newlines cannot break the markdown link.

Non-commerce `ItemList` payloads — rows carrying neither a lifted `price` nor `url` — SHALL keep the existing fixed-width markdown table rendering, unchanged.

#### Scenario: Product ItemList renders to linked records with price and url

- **WHEN** a thin page carries a JSON-LD `ItemList` whose `itemListElement` entries are `Product` items with `offers.{price, priceCurrency, url}`
- **THEN** `json_to_markdown_rows` renders one linked-record line per item, each carrying the item name as link text, the full un-truncated product url as the link target, and a combined `<price> <currency>` token (e.g. `3690 TRY`); no image-CDN url appears in the output

#### Scenario: Long product url is preserved verbatim

- **WHEN** a `Product` item's `offers.url` exceeds the fixed-width table's 80-character cell cap
- **THEN** the rendered linked record contains the complete url with no truncation

#### Scenario: aggregateRating is lifted when present

- **WHEN** a `Product` item carries `aggregateRating.ratingValue`
- **THEN** the rendered record includes the rating; items without a rating render without one and are not malformed

#### Scenario: Non-commerce ItemList keeps table rendering

- **WHEN** an `ItemList` carries rows that have neither a lifted `price` nor `url` (e.g. a generic index list)
- **THEN** `json_to_markdown_rows` renders the existing fixed-width markdown table, not linked records

#### Scenario: Empty ItemList yields no rows

- **WHEN** the `ItemList` is empty or malformed
- **THEN** the adapter yields no rows and the ladder continues to the next source
