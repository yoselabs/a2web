## MODIFIED Requirements

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

### Requirement: timing, cache, diagnostics, and tokens are debug-only on FetchResponse

`FetchResponse` SHALL expose all debug-tier observability through a single `debug` sub-object, not as scattered top-level keys. The `debug` object SHALL carry `started_at`, `total_ms`, `cache`, `diagnostics`, and `tokens`. The `debug` key SHALL appear on the wire only when `fetch_raw` is called with `debug=True`; with `debug=False` it SHALL be absent. No `started_at`, `total_ms`, `cache`, `diagnostics`, or `tokens` key SHALL appear at the top level of the envelope.

#### Scenario: default fetch_raw omits the debug sub-object

- **WHEN** `fetch_raw` is called with `debug=False`
- **THEN** the wire payload contains no `debug` key, and no `started_at`, `total_ms`, `cache`, `diagnostics`, or `tokens` key at the top level

#### Scenario: debug fetch_raw nests the full trace under debug

- **WHEN** `fetch_raw` is called with `debug=True`
- **THEN** the wire payload contains a `debug` object carrying `started_at`, `total_ms`, `cache`, `tokens`, and the `diagnostics` trace

## ADDED Requirements

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
