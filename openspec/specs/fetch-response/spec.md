# fetch-response Specification

## Purpose
TBD - created by archiving change fetch-response-diet. Update Purpose after archive.
## Requirements
### Requirement: FetchResponse omits empty optional fields from the wire

The `FetchResponse` serializer SHALL omit optional fields whose value is `None`, an empty list, an empty dict, or an empty string. The optional fields subject to omission are `title`, `byline`, `published`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, and `extracted_answer`. `FetchResponse` SHALL NOT declare `original_url`. The field `confidence` SHALL always be present; `tier` and `url` each appear only when they deviate from their default and are governed by their own requirements.

#### Scenario: null and empty optionals do not reach the wire

- **WHEN** `fetch_raw` completes successfully against a page with no byline, no metadata, no links, and no LLM extraction
- **THEN** the wire payload contains no `byline`, `published`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, `extracted_answer`, or `original_url` key

#### Scenario: confidence is always present

- **WHEN** any `fetch_raw` invocation completes
- **THEN** the wire payload contains `confidence`

#### Scenario: populated optionals are present

- **WHEN** `fetch_raw` completes against a page that yields a title and metadata
- **THEN** the wire payload contains `title` and `meta` with their non-empty contents

### Requirement: status is failure-only on FetchResponse

`FetchResponse` SHALL include `status` on the wire only when its value is not `ok` — i.e. on a `failed` or `partial` fetch. On a successful `fetch_raw`, `status` SHALL be absent; consumers SHALL interpret its absence as success.

#### Scenario: successful fetch_raw omits status

- **WHEN** `fetch_raw` completes with a successful fetch
- **THEN** the wire payload contains no `status` key

#### Scenario: failed fetch_raw carries status

- **WHEN** `fetch_raw` completes with a failed fetch
- **THEN** the wire payload contains `status` with the value `failed`

### Requirement: narrative and diagnostics_summary are failure-only on FetchResponse

`FetchResponse` SHALL include `narrative` and `diagnostics_summary` only when `status != ok`. On a successful `fetch_raw` they SHALL be absent from the wire payload.

#### Scenario: successful fetch_raw omits narrative

- **WHEN** `fetch_raw` completes successfully
- **THEN** the wire payload contains no `narrative` and no `diagnostics_summary` key

#### Scenario: failed fetch_raw carries the failure explanation

- **WHEN** `fetch_raw` completes with a failed fetch
- **THEN** the wire payload contains `narrative` and `diagnostics_summary` describing the failure

### Requirement: timing, cache, diagnostics, and tokens are debug-only on FetchResponse

`FetchResponse` SHALL expose all debug-tier observability through a single `debug` sub-object, not as scattered top-level keys. The `debug` object SHALL carry `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and `content_candidates`. The `content_candidates` entry SHALL be the list of extraction-input candidates the page produced — each rendered as `{source, content_md}` — exposing exactly the menu the server-side extractor was fed. The `debug` key SHALL appear on the wire only when `fetch_raw` (or `ask`) is called with `debug=True`; with `debug=False` it SHALL be absent. No `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `content_candidates` key SHALL appear at the top level of the envelope. `content_candidates` SHALL remain a flat attribute on the model for internal callers; only the wire serializer regroups it under `debug`.

#### Scenario: default fetch_raw omits the debug sub-object

- **WHEN** `fetch_raw` is called with `debug=False`
- **THEN** the wire payload contains no `debug` key, and no `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `content_candidates` key at the top level

#### Scenario: debug fetch_raw nests the full trace under debug

- **WHEN** `fetch_raw` is called with `debug=True`
- **THEN** the wire payload contains a `debug` object carrying `started_at`, `total_ms`, `cache`, `tokens`, the `diagnostics` trace, and `content_candidates`

#### Scenario: content_candidates surfaces the extractor menu

- **WHEN** `fetch_raw` is called with `debug=True` against a page that produced multiple extraction candidates
- **THEN** the `debug.content_candidates` list carries one `{source, content_md}` entry per candidate fed to the extractor, in the menu's source order

### Requirement: links and next_links render as TSV blocks on FetchResponse

When `FetchResponse.links` or `FetchResponse.next_links` is non-empty, the serializer SHALL render it on the wire as a TSV string — a tab-separated header row followed by one tab-separated row per entry. `links` columns SHALL be `anchor`, `href`, `role`; `next_links` columns SHALL be `anchor`, `url`, `reason`, `kind`, with the `kind` column omitted when every entry's `kind` is `drilldown`. An empty `links` or `next_links` SHALL remain absent from the wire payload.

#### Scenario: populated links render as TSV

- **WHEN** `fetch_raw` is called with `include_links=True` against a page with links
- **THEN** the wire `links` is a TSV string whose header row is `anchor`, `href`, `role`, followed by one row per link

#### Scenario: next_links render as TSV

- **WHEN** `fetch_raw` completes with a non-empty `next_links` list
- **THEN** the wire `next_links` is a TSV string with a header row and one row per candidate

#### Scenario: empty link arrays stay absent

- **WHEN** `fetch_raw` completes with no links and no next-link candidates
- **THEN** the wire payload contains no `links` and no `next_links` key

### Requirement: the empty-omission serializer is shared with AskResponse

The empty-field omission and TSV-rendering logic SHALL be implemented once as a shared helper and reused by both the `AskResponse` and `FetchResponse` serializers, parameterized by each envelope's required-field set and TSV-field set. The two serializers SHALL NOT carry duplicated omission logic.

#### Scenario: both envelopes prune via the same helper

- **WHEN** the `AskResponse` and `FetchResponse` serializers run
- **THEN** both delegate empty-omission and TSV rendering to the same shared helper function

### Requirement: tier is deviation-only on FetchResponse

`FetchResponse` SHALL include `tier` on the wire only when its value is not `raw` — i.e. when the content came from a site handler, the Jina reader, the archive fallback, or the browser tier. On a plain raw HTTP fetch (`tier == "raw"`), `tier` SHALL be absent; consumers SHALL interpret its absence as a plain raw fetch.

#### Scenario: raw-tier fetch omits tier

- **WHEN** `fetch_raw` completes with the content served by the `raw` tier
- **THEN** the wire payload contains no `tier` key

#### Scenario: non-raw tier is carried

- **WHEN** `fetch_raw` completes with the content served by a site handler (e.g. `site_handler:hn`)
- **THEN** the wire payload contains `tier` with that tier identifier

### Requirement: url is redirect-only on FetchResponse

`FetchResponse` SHALL include `url` on the wire only when the fetched URL differs from the URL the caller requested — i.e. when an HTTP redirect or a captcha-host rewrite changed the destination. When the fetch landed exactly on the requested URL, `url` SHALL be absent; consumers SHALL interpret its absence as "the fetch landed on the URL I requested."

#### Scenario: no-redirect fetch omits url

- **WHEN** `fetch_raw` completes and the fetched URL equals the requested URL
- **THEN** the wire payload contains no `url` key

#### Scenario: redirected fetch carries the final url

- **WHEN** `fetch_raw` completes and the fetch was redirected or the host was rewritten
- **THEN** the wire payload contains `url` with the final fetched URL

### Requirement: retrieval_incomplete envelope field
`FetchResponse` (and the projected `AskResponse`) SHALL carry a `retrieval_incomplete` boolean that is true when the requested URL's content was not retrieved due to a wall. The field SHALL be present on the wire whenever true and MAY be omitted when false (absence means retrieval was complete).

#### Scenario: Field present on walled fetch
- **WHEN** a fetch is walled
- **THEN** the serialized envelope includes `retrieval_incomplete: true`

#### Scenario: Field absent on success
- **WHEN** a fetch succeeds
- **THEN** the envelope omits `retrieval_incomplete` (or sets it false)

### Requirement: OperatorHint severity
`OperatorHint` SHALL gain a `severity` field (at least `info` and `critical`). A `try_user_browser` hint SHALL be `critical`. Existing hints without an explicit severity default to `info` (backward-compatible).

#### Scenario: Browser hint is critical
- **WHEN** a `try_user_browser` hint is emitted
- **THEN** its `severity` is `critical`

#### Scenario: Existing hints stay info
- **WHEN** a pre-existing hint (e.g. `cookies_stale`) is emitted without an explicit severity
- **THEN** its severity defaults to `info` and existing behavior is unchanged

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

