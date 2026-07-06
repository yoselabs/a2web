## ADDED Requirements

### Requirement: Fetch envelope carries listing item counts

The `FetchResponse` envelope (returned by `fetch_raw`) SHALL carry optional
`items_loaded` and `items_total` fields and a `listing_partial` operator hint on
a partial listing, on the same terms as the `ask` envelope, pruned from the wire
when absent. Because `fetch_raw` runs no LLM and drives no render escalation, the
signal is diagnostic-only on this path — the counts and hint surface, but no
scroll-to-complete is attempted.

#### Scenario: fetch_raw surfaces the partial signal without scrolling

- **WHEN** a `fetch_raw` over a listing parses 31 records against an oracle of 40
- **THEN** the response carries `items_loaded: 31`, `items_total: 40`, and a `listing_partial` info hint, and no scrolling render is attempted
