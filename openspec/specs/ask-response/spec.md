# ask-response Specification

## Purpose
TBD - created by archiving change ask-response-diet. Update Purpose after archive.
## Requirements
### Requirement: ask returns the lean AskResponse envelope

The `ask` tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL NOT declare `fit_md`, `tokens`, or `is_user_authored`. `AskResponse` SHALL always carry `url`, `tier`, `confidence`, and `extracted_answer`; these required fields SHALL never be omitted from the wire. `status` is failure-only and is governed by its own requirement.

#### Scenario: ask success carries the answer and required fields

- **WHEN** `ask` completes successfully against a fixture page with a question
- **THEN** the returned envelope is an `AskResponse` with `url`, `tier`, `confidence`, and `extracted_answer` populated, and has no `fit_md`, `tokens`, or `is_user_authored` field

#### Scenario: ask never exposes fit_md or is_user_authored

- **WHEN** any `ask` invocation completes
- **THEN** the serialized wire payload contains no `fit_md` and no `is_user_authored` key

### Requirement: content_md is opt-in on ask

`AskResponse` SHALL omit `content_md` and `headings` by default. The `ask` tool SHALL accept an `include_content: bool` parameter defaulting to `False`. When `include_content` is `False`, `content_md` and `headings` SHALL be absent from the wire payload. When `include_content` is `True`, `content_md` (wrapped per the existing untrusted-content rule) and `headings` SHALL be populated.

#### Scenario: default ask omits page content

- **WHEN** `ask` is called without `include_content`
- **THEN** the wire payload contains no `content_md` and no `headings` key

#### Scenario: include_content=True returns grounding content

- **WHEN** `ask` is called with `include_content=True` against a fixture page
- **THEN** the wire payload contains `content_md` with the wrapped page markdown and `headings` with the extracted heading list

### Requirement: empty optional fields are omitted from the wire

The `AskResponse` serializer SHALL omit optional fields whose value is `None`, an empty list, an empty dict, or an empty string. The optional fields subject to omission are `title`, `byline`, `published`, `operator_hints`, `next_links`, `original_url`, and `meta`. Required fields SHALL never be omitted regardless of value.

#### Scenario: null and empty optionals do not reach the wire

- **WHEN** `ask` completes with no byline, no published date, no operator hints, no next links, and no URL rewrite
- **THEN** the wire payload contains no `byline`, `published`, `operator_hints`, `next_links`, `original_url`, or `meta` key

#### Scenario: populated optionals are present

- **WHEN** `ask` completes against a page that produces operator hints and next links
- **THEN** the wire payload contains `operator_hints` and `next_links` with their non-empty contents

#### Scenario: omission survives the formatter wire path

- **WHEN** `ask` is invoked through the in-process test client (the production formatter wrapper chain)
- **THEN** the marshaled result has the empty optional fields absent, not present as `null` / `[]` / `{}`

### Requirement: narrative and diagnostics_summary are failure-only on ask

`AskResponse` SHALL include `narrative` and `diagnostics_summary` only when `status != ok`. On a successful `ask` they SHALL be absent from the wire payload.

#### Scenario: successful ask omits narrative

- **WHEN** `ask` completes with `status == ok`
- **THEN** the wire payload contains no `narrative` and no `diagnostics_summary` key

#### Scenario: failed ask carries the failure explanation

- **WHEN** `ask` completes with `status == failed`
- **THEN** the wire payload contains `narrative` and `diagnostics_summary` describing the failure

### Requirement: timing and cache fields are debug-only on ask

`AskResponse` SHALL include `started_at`, `total_ms`, `cache`, and `diagnostics` only when the tool is called with `debug=True`. With `debug=False` these fields SHALL be absent from the wire payload.

#### Scenario: default ask omits timing metadata

- **WHEN** `ask` is called with `debug=False`
- **THEN** the wire payload contains no `started_at`, `total_ms`, `cache`, or `diagnostics` key

#### Scenario: debug ask includes the full trace

- **WHEN** `ask` is called with `debug=True`
- **THEN** the wire payload contains `started_at`, `total_ms`, `cache`, and the `diagnostics` trace

### Requirement: extraction metadata on ask is slimmed to agent-relevant signal

`AskResponse.extraction` SHALL be absent from the wire payload when `debug=False`. The full extraction metadata (`truncated`, `model`, `template_name`, token counts, `cost_usd`, `latency_ms`, `cache_hit`) SHALL be exposed only when `debug=True`. The full metadata SHALL remain available on LDD events regardless of `debug`.

When the extractor truncated its input (the fetched content exceeded the extractor's character cap, so the answer was produced from a partial read), `ask` SHALL append an `OperatorHint` with `code` `"answer_truncated"` to `operator_hints`, regardless of `debug`. The zero-information `extraction: {"truncated": false}` object SHALL NOT appear on any wire payload.

#### Scenario: default ask omits extraction entirely

- **WHEN** `ask` completes with `debug=False` and the extractor ran without truncation
- **THEN** the wire payload contains no `extraction` key

#### Scenario: truncation surfaces as an operator hint

- **WHEN** `ask` completes with `debug=False` and the extractor truncated its input
- **THEN** the wire payload contains no `extraction` key, and `operator_hints` contains an entry with `code == "answer_truncated"`

#### Scenario: debug ask exposes full extraction metadata

- **WHEN** `ask` completes with `debug=True` and the extractor ran
- **THEN** the wire `extraction` carries `truncated`, `model`, `template_name`, token counts, `cost_usd`, `latency_ms`, and `cache_hit`

### Requirement: status is failure-only on ask

`AskResponse` SHALL include `status` on the wire only when its value is not `ok` — i.e. on a `failed` or `partial` fetch. On a successful `ask`, `status` SHALL be absent from the wire payload. Consumers SHALL interpret the absence of `status` as success (`ok`).

#### Scenario: successful ask omits status

- **WHEN** `ask` completes with a successful fetch
- **THEN** the wire payload contains no `status` key

#### Scenario: failed ask carries status

- **WHEN** `ask` completes with a failed fetch
- **THEN** the wire payload contains `status` with the value `failed`

### Requirement: next_links renders as a TSV block on ask

When `AskResponse.next_links` is non-empty, the serializer SHALL render it on the wire as a TSV string — a tab-separated header row followed by one tab-separated row per link. The columns SHALL be `anchor`, `url`, `reason`, and `kind`. The `kind` column SHALL be omitted when every link's `kind` is `drilldown`, and SHALL be included when the list contains a mix of kinds. An empty `next_links` SHALL remain absent from the wire payload.

#### Scenario: all-drilldown next_links renders TSV without the kind column

- **WHEN** `ask` completes with a `next_links` list where every entry has `kind == "drilldown"`
- **THEN** the wire `next_links` is a TSV string whose header row is `anchor`, `url`, `reason` (no `kind` column), followed by one row per link

#### Scenario: mixed-kind next_links keeps the kind column

- **WHEN** `ask` completes with a `next_links` list containing more than one distinct `kind`
- **THEN** the wire `next_links` is a TSV string whose header row includes the `kind` column

#### Scenario: empty next_links stays absent

- **WHEN** `ask` completes with no next-link candidates
- **THEN** the wire payload contains no `next_links` key
