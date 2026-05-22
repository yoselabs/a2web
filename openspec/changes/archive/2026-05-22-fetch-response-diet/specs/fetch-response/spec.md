## ADDED Requirements

### Requirement: FetchResponse omits empty optional fields from the wire

The `FetchResponse` serializer SHALL omit optional fields whose value is `None`, an empty list, an empty dict, or an empty string. The optional fields subject to omission are `title`, `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, and `extracted_answer`. The fields `url`, `tier`, and `confidence` SHALL always be present.

#### Scenario: null and empty optionals do not reach the wire

- **WHEN** `fetch_raw` completes successfully against a page with no byline, no metadata, no links, and no LLM extraction
- **THEN** the wire payload contains no `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, or `extracted_answer` key

#### Scenario: required fields are always present

- **WHEN** any `fetch_raw` invocation completes
- **THEN** the wire payload contains `url`, `tier`, and `confidence`

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

`FetchResponse` SHALL include `started_at`, `total_ms`, `cache`, `diagnostics`, and `tokens` only when `fetch_raw` is called with `debug=True`. With `debug=False` these fields SHALL be absent from the wire payload.

#### Scenario: default fetch_raw omits timing metadata

- **WHEN** `fetch_raw` is called with `debug=False`
- **THEN** the wire payload contains no `started_at`, `total_ms`, `cache`, `diagnostics`, or `tokens` key

#### Scenario: debug fetch_raw includes the full trace

- **WHEN** `fetch_raw` is called with `debug=True`
- **THEN** the wire payload contains `started_at`, `total_ms`, `cache`, `tokens`, and the `diagnostics` trace

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
