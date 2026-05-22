## MODIFIED Requirements

### Requirement: ask returns the lean AskResponse envelope

The `ask` tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL NOT declare `fit_md`, `tokens`, `is_user_authored`, or `original_url`. `AskResponse` SHALL always carry `confidence` and `extracted_answer`; these required fields SHALL never be omitted from the wire. `status`, `tier`, and `url` each appear only when they deviate from their default and are governed by their own requirements.

#### Scenario: ask success carries the answer and required fields

- **WHEN** `ask` completes successfully against a fixture page with a question
- **THEN** the returned envelope is an `AskResponse` with `confidence` and `extracted_answer` populated, and has no `fit_md`, `tokens`, `is_user_authored`, or `original_url` field

#### Scenario: ask never exposes fit_md or is_user_authored

- **WHEN** any `ask` invocation completes
- **THEN** the serialized wire payload contains no `fit_md` and no `is_user_authored` key

### Requirement: empty optional fields are omitted from the wire

The `AskResponse` serializer SHALL omit optional fields whose value is `None`, an empty list, an empty dict, or an empty string. The optional fields subject to omission are `title`, `byline`, `published`, `operator_hints`, `next_links`, and `meta`. Required fields SHALL never be omitted regardless of value.

#### Scenario: null and empty optionals do not reach the wire

- **WHEN** `ask` completes with no byline, no published date, no operator hints, and no next links
- **THEN** the wire payload contains no `byline`, `published`, `operator_hints`, `next_links`, or `meta` key

#### Scenario: populated optionals are present

- **WHEN** `ask` completes against a page that produces operator hints and next links
- **THEN** the wire payload contains `operator_hints` and `next_links` with their non-empty contents

#### Scenario: omission survives the formatter wire path

- **WHEN** `ask` is invoked through the in-process test client (the production formatter wrapper chain)
- **THEN** the marshaled result has the empty optional fields absent, not present as `null` / `[]` / `{}`

### Requirement: debug observability is a single debug sub-object on ask

`AskResponse` SHALL expose all debug-tier observability through a single `debug` sub-object, not as scattered top-level keys. The `debug` object SHALL carry `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and `extraction`. The `debug` key SHALL appear on the wire only when the tool is called with `debug=True`; with `debug=False` it SHALL be absent. No `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `extraction` key SHALL appear at the top level of the envelope.

#### Scenario: default ask omits the debug sub-object

- **WHEN** `ask` is called with `debug=False`
- **THEN** the wire payload contains no `debug` key, and no `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `extraction` key at the top level

#### Scenario: debug ask nests the full trace under debug

- **WHEN** `ask` is called with `debug=True`
- **THEN** the wire payload contains a `debug` object carrying `started_at`, `total_ms`, `cache`, `tokens`, and the `diagnostics` trace

### Requirement: extraction metadata on ask is slimmed to agent-relevant signal

`AskResponse` SHALL NOT expose `extraction` at the top level of the envelope. The full extraction metadata (`truncated`, `model`, `template_name`, token counts, `cost_usd`, `latency_ms`, `cache_hit`) SHALL be exposed only inside the `debug` sub-object, only when `debug=True`. The full metadata SHALL remain available on LDD events regardless of `debug`.

When the extractor truncated its input (the fetched content exceeded the extractor's character cap, so the answer was produced from a partial read), `ask` SHALL append an `OperatorHint` with `code` `"answer_truncated"` to `operator_hints`, regardless of `debug`. The zero-information `extraction: {"truncated": false}` object SHALL NOT appear on any wire payload.

#### Scenario: default ask omits extraction entirely

- **WHEN** `ask` completes with `debug=False` and the extractor ran without truncation
- **THEN** the wire payload contains no `extraction` key and no `debug` key

#### Scenario: truncation surfaces as an operator hint

- **WHEN** `ask` completes with `debug=False` and the extractor truncated its input
- **THEN** the wire payload contains no `extraction` key, and `operator_hints` contains an entry with `code == "answer_truncated"`

#### Scenario: debug ask exposes full extraction metadata under debug

- **WHEN** `ask` completes with `debug=True` and the extractor ran
- **THEN** the `debug` object carries an `extraction` with `truncated`, `model`, `template_name`, token counts, `cost_usd`, `latency_ms`, and `cache_hit`

## ADDED Requirements

### Requirement: tier is deviation-only on ask

`AskResponse` SHALL include `tier` on the wire only when its value is not `raw` — i.e. when the content came from a site handler, the Jina reader, the archive fallback, or the browser tier. On a plain raw HTTP fetch (`tier == "raw"`), `tier` SHALL be absent; consumers SHALL interpret its absence as a plain raw fetch.

#### Scenario: raw-tier fetch omits tier

- **WHEN** `ask` completes with the content served by the `raw` tier
- **THEN** the wire payload contains no `tier` key

#### Scenario: non-raw tier is carried

- **WHEN** `ask` completes with the content served by a site handler (e.g. `site_handler:hn`)
- **THEN** the wire payload contains `tier` with that tier identifier

### Requirement: url is redirect-only on ask

`AskResponse` SHALL include `url` on the wire only when the fetched URL differs from the URL the caller requested — i.e. when an HTTP redirect or a captcha-host rewrite changed the destination. When the fetch landed exactly on the requested URL, `url` SHALL be absent; consumers SHALL interpret its absence as "the fetch landed on the URL I requested."

#### Scenario: no-redirect fetch omits url

- **WHEN** `ask` completes and the fetched URL equals the requested URL
- **THEN** the wire payload contains no `url` key

#### Scenario: redirected fetch carries the final url

- **WHEN** `ask` completes and the fetch was redirected or the host was rewritten
- **THEN** the wire payload contains `url` with the final fetched URL
