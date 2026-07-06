# ask-response Specification

## Purpose
TBD - created by archiving change ask-response-diet. Update Purpose after archive.
## Requirements
### Requirement: ask returns the lean AskResponse envelope

The `ask` tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL NOT declare `fit_md`, `tokens`, `is_user_authored`, or `original_url`. `AskResponse` SHALL always carry `confidence` and `extracted_answer`; these required fields SHALL never be omitted from the wire. `status`, `tier`, and `url` each appear only when they deviate from their default and are governed by their own requirements.

#### Scenario: ask success carries the answer and required fields

- **WHEN** `ask` completes successfully against a fixture page with a question
- **THEN** the returned envelope is an `AskResponse` with `confidence` and `extracted_answer` populated, and has no `fit_md`, `tokens`, `is_user_authored`, or `original_url` field

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

### Requirement: narrative and diagnostics_summary are failure-only on ask

`AskResponse` SHALL include `narrative` and `diagnostics_summary` only when `status != ok`. On a successful `ask` they SHALL be absent from the wire payload.

#### Scenario: successful ask omits narrative

- **WHEN** `ask` completes with `status == ok`
- **THEN** the wire payload contains no `narrative` and no `diagnostics_summary` key

#### Scenario: failed ask carries the failure explanation

- **WHEN** `ask` completes with `status == failed`
- **THEN** the wire payload contains `narrative` and `diagnostics_summary` describing the failure

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

### Requirement: AskResponse carries router-shape fields by default

`AskResponse` SHALL declare seven router-shape fields replacing the v0.20 `affordances` field:

Required fields (always present on the wire when the LLM extractor returned a routing payload):
- `answer: str` — the model's answer to the question.
- `structural_form: Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]` — what the page IS structurally.
- `shape: Literal["prose","records","key-value","code","table","discussion","mixed"]` — the data shape of the answer-bearing content.

Conditional fields (omitted from the wire via `_prune_wire` when empty/null):
- `genre: Literal["news","encyclopedia","spec","paper","personal","official","community"] | None` — what the page is ABOUT; omitted when no value clearly applies.
- `obstacle: Literal["paywalled","blocked","empty","error"] | None` — page-level failure mode; omitted on healthy pages.
- `ask_here: list[str]` — same-URL re-asks; omitted when `[]`.
- `try_url: list[NextUrl]` — different-URL re-asks where each entry has `{url, reason}`; omitted when `[]`.

The `ask` tool SHALL accept an `include_routing: bool` parameter defaulting to `True`. When `include_routing=False`, all seven fields SHALL be `None` / absent and the wire SHALL carry the lean v0.14 envelope shape. When `include_routing=True` but the extractor returned no routing payload (no LLM, fetch error, parse failure), all seven fields SHALL be absent.

#### Scenario: Default ask includes the router-shape fields

- **WHEN** `ask` is called without `include_routing` against a content page that the LLM successfully extracts
- **THEN** the wire carries `answer`, `structural_form`, `shape` always, plus `genre` / `obstacle` / `ask_here` / `try_url` only when populated

#### Scenario: Opt-out via include_routing=False suppresses all seven fields

- **WHEN** `ask` is called with `include_routing=False`
- **THEN** the wire carries no `structural_form`, `shape`, `genre`, `obstacle`, `ask_here`, or `try_url` keys (and `answer` remains the unstructured extractor answer)

#### Scenario: Extractor unavailable leaves router fields absent

- **WHEN** `ask` is called with `include_routing=True` but the LLM extractor is unavailable
- **THEN** the wire carries none of the seven router-shape fields, and an `operator_hint` with `code="llm_unavailable"` records the reason

### Requirement: RouterPayload uses closed enums on every typed field

The `RouterPayload` pydantic model SHALL declare each typing field as a typed `Literal`:

- `structural_form` — `Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]` (9 values, required).
- `shape` — `Literal["prose","records","key-value","code","table","discussion","mixed"]` (7 values, required).
- `genre` — `Literal["news","encyclopedia","spec","paper","personal","official","community"] | None` (7 values, optional).
- `obstacle` — `Literal["paywalled","blocked","empty","error"] | None` (4 values, optional).

`NextUrl.url` SHALL be a string. `NextUrl.reason` SHALL be a string. Values outside the closed enums SHALL be rejected by pydantic validation at the model boundary, and the boundary projection SHALL leave the seven router-shape fields absent on validation failure (the answer text on `AskResponse.answer` is unaffected).

#### Scenario: Closed structural_form rejects unknown values

- **WHEN** an extractor response carries `structural_form: "blog-post"` (a v0.20-era label not in the new enum)
- **THEN** the boundary projection raises a pydantic validation error, all seven router-shape fields are absent from `AskResponse`, and `answer` carries the extractor's answer text unchanged

#### Scenario: Closed shape rejects unknown values

- **WHEN** an extractor response carries `shape: "diagram"`
- **THEN** the boundary projection raises a pydantic validation error and the seven router-shape fields are absent

#### Scenario: Optional fields accept None and string values

- **WHEN** an extractor response carries `genre: null` and no `obstacle` key
- **THEN** `RouterPayload.genre` resolves to `None`, `RouterPayload.obstacle` resolves to `None`, and both fields are absent from the wire

### Requirement: Router-shape envelope omits empty conditional fields via _prune_wire

The `AskResponse._prune_wire` serializer SHALL treat the four conditional router-shape fields as omit-empty:

- `genre` is omitted when `None`.
- `obstacle` is omitted when `None`.
- `ask_here` is omitted when `[]`.
- `try_url` is omitted when `[]`.

The three required fields (`answer`, `structural_form`, `shape`) SHALL always appear when present on the model.

#### Scenario: Healthy article with complete answer omits all four conditionals

- **WHEN** `ask` returns a routing payload with `obstacle=None`, `genre=None`, `ask_here=[]`, `try_url=[]`
- **THEN** the wire payload contains exactly `answer`, `structural_form`, `shape`, plus the rest of the AskResponse envelope; no `genre`, `obstacle`, `ask_here`, or `try_url` keys

#### Scenario: Obstacle page populates obstacle and try_url

- **WHEN** `ask` returns a routing payload with `obstacle="paywalled"` and `try_url=[{...}]`
- **THEN** the wire contains both keys, plus `answer`, `structural_form`, `shape`, with `genre` and `ask_here` omitted if not populated

#### Scenario: Field shape survives the formatter wire path

- **WHEN** `ask` with the router-shape is invoked through the in-process test client (production formatter wrapper chain)
- **THEN** the marshaled result has omit-empty conditionals absent (not present as `null` or `[]`)

### Requirement: confidence reflects the extractor obstacle signal on ask

On the `ask` path, `confidence` MUST NOT be derived solely from `(verdict, content length)`. When the extractor reports an `obstacle`, the response SHALL downgrade confidence: an `obstacle` in `{empty, blocked, paywalled, error}` caps `confidence` at `low`. The downgrade is one-directional — an `obstacle` may only lower confidence, never raise it. Because `obstacle` is produced after the base response is built (in the answer-extraction phase), this reconciliation is applied where `obstacle` reaches the wire (the ask-path projection), and applies only to `ask` (the `fetch_raw` envelope has no `obstacle`).

#### Scenario: Empty obstacle caps a would-be high confidence

- **WHEN** an `ask` fetch returns `verdict == ok` over more than 2000 characters of rendered content (which alone would yield `confidence: high`) but the extractor reports `obstacle: "empty"`
- **THEN** the wire `confidence` is `low`

#### Scenario: Blocked obstacle caps confidence

- **WHEN** an `ask` fetch reports `obstacle: "blocked"`
- **THEN** the wire `confidence` is `low`

#### Scenario: Healthy page keeps its computed confidence

- **WHEN** an `ask` fetch returns `verdict == ok` over rich content and the extractor omits `obstacle` (healthy page)
- **THEN** `confidence` is unchanged from its `(verdict, content length)` derivation

#### Scenario: fetch_raw is unaffected

- **WHEN** a `fetch_raw` request completes
- **THEN** confidence derivation is unchanged — no `obstacle` reconciliation is applied (fetch_raw carries no obstacle)

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

