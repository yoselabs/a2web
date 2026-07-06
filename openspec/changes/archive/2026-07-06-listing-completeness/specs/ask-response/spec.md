## ADDED Requirements

### Requirement: Ask envelope carries listing item counts

The `AskResponse` envelope SHALL carry optional `items_loaded` and `items_total`
fields, mirroring the existing `comments_loaded` / `comments_total` pair, set
only when the fetched page is a listing with a measured record count (and, for
`items_total`, an extracted oracle). Both fields SHALL be pruned from the wire
when absent. A partial listing SHALL additionally carry a `listing_partial`
operator hint at `severity: info`; this SHALL NOT flip `confidence` to `low` nor
set `retrieval_incomplete` (a partial listing returned real records — it is an
honest info signal, distinct from the obstacle/wall confidence machinery).

#### Scenario: Partial listing populates item counts

- **WHEN** an `ask` over a listing parses 31 records against an oracle of 40
- **THEN** the `ask` response carries `items_loaded: 31`, `items_total: 40`, and a `listing_partial` info hint
- **AND** `confidence` is unchanged and `retrieval_incomplete` is not set

#### Scenario: Non-listing ask omits the fields

- **WHEN** an `ask` over an article produces no `RecordSet`
- **THEN** `items_loaded` / `items_total` are absent from the wire and no `listing_partial` hint is present
