## MODIFIED Requirements

### Requirement: ask returns the lean AskResponse envelope

The primary extraction tool SHALL be named `query` (renamed from `ask`) and SHALL take a `query` parameter (renamed from `question`). The tool SHALL keep its bare canonical name via `canonical_name_override="query"`. The tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL NOT declare `fit_md`, `tokens`, `is_user_authored`, or `original_url`. `AskResponse` SHALL always carry `confidence` and the answer field (`answer`); these required fields SHALL never be omitted from the wire. `status`, `tier`, and `url` each appear only when they deviate from their default and are governed by their own requirements. The `query` parameter's tool description SHALL teach the query grammar (per `Follow-up suggestions render as queries`) and SHALL state the cost asymmetry (per `also_here and other_pages are governed by the withheld-body index`).

#### Scenario: tool advertises the bare name

- **WHEN** the MCP `list_tools` is served
- **THEN** the primary extraction tool is advertised as `query` (not `ask`, not `web_query`)

#### Scenario: ask success carries the answer and required fields

- **WHEN** `query` completes successfully against a fixture page with a query
- **THEN** the returned envelope is an `AskResponse` with `confidence` and `answer` populated, and has no `fit_md`, `tokens`, `is_user_authored`, or `original_url` field

#### Scenario: ask never exposes fit_md or is_user_authored

- **WHEN** any `query` invocation completes
- **THEN** the serialized wire payload contains no `fit_md` and no `is_user_authored` key

### Requirement: AskResponse carries router-shape fields by default

`AskResponse` SHALL declare the router-shape fields (`structural_form` and `shape` are not projected onto the wire):

Required field (always present on the wire when the LLM extractor returned a routing payload):
- `answer: str` — the model's answer to the query.

Conditional fields (omitted from the wire via `_prune_wire` when empty/null):
- `obstacle: Literal["paywalled","blocked","empty","error"] | None` — page-level failure mode; omitted on healthy pages.
- `also_here: list[str]` — the same-page index (renamed from `ask_here`), query-grammar strings (per `Follow-up suggestions render as queries`), NOT full questions; omitted when `[]`.
- `other_pages: list[OtherPage]` — off-page pointers (replacing both `next_links` and `try_url`), kind-tagged `structural`|`drilldown` per `other_pages unifies next_links and try_url`; omitted when `[]`.

`AskResponse` SHALL NOT declare a `genre` field, and SHALL NOT declare `structural_form` or `shape` fields. `RouterPayload` (the internal LLM-parse boundary type) still requires `structural_form` and `shape` from the extractor, and internal consumers (`content_guidance.kind_guidance()`, the `refinement_axes` gate) continue reading `routing.structural_form` directly; only the wire projection onto `AskResponse` is removed. `obstacle` stays on the wire — it has a real consumer (the incompleteness gate).

The `query` tool SHALL accept an `include_routing: bool` parameter defaulting to `True`. When `include_routing=False`, the router-shape fields SHALL be `None` / absent and the wire SHALL carry the lean envelope shape. When `include_routing=True` but the extractor returned no routing payload (no LLM, fetch error, parse failure), the router-shape fields SHALL be absent.

#### Scenario: Default ask includes the router-shape fields

- **WHEN** `query` is called without `include_routing` against a content page that the LLM successfully extracts
- **THEN** the wire carries `answer` always, plus `obstacle` / `also_here` / `other_pages` only when populated, and no `genre`, `structural_form`, or `shape` key under any circumstance

#### Scenario: also_here replaces ask_here on the wire

- **WHEN** `query` returns a routing payload with a populated same-page index
- **THEN** the wire carries `also_here` (never `ask_here`) as a list of query-grammar strings

#### Scenario: empty also_here is omitted

- **WHEN** the same-page index is empty
- **THEN** the wire carries no `also_here` key (and no `ask_here` key under any circumstance)

#### Scenario: Opt-out via include_routing=False suppresses all four fields

- **WHEN** `query` is called with `include_routing=False`
- **THEN** the wire carries no `obstacle`, `also_here`, or `other_pages` keys (and `answer` remains the unstructured extractor answer)

#### Scenario: Extractor unavailable leaves router fields absent

- **WHEN** `query` is called with `include_routing=True` but the LLM extractor is unavailable
- **THEN** the wire carries none of the router-shape fields, and an `operator_hint` with `code="llm_unavailable"` records the reason

#### Scenario: structural_form and shape never reach the wire even though RouterPayload requires them

- **WHEN** `query` is called against a page the LLM classifies as `structural_form: "product"`, `shape: "key-value"`
- **THEN** `RouterPayload.structural_form` and `RouterPayload.shape` are populated internally (consumed by `content_guidance.kind_guidance()` to emit the `content_guidance` operator hint), but neither `structural_form` nor `shape` appears as a key on the `AskResponse` wire

## ADDED Requirements

### Requirement: also_here and other_pages are governed by the withheld-body index

Per ADR-0015, `also_here` SHALL be an index of on-page content that did NOT reach the `answer` (certain, cheap to recover via a cache-served same-URL re-query), and SHALL NOT be present when the answer already covered the page. `also_here` SHALL be dense on prose/product/discussion pages and sparse on a `listing` (where `options` + `refinement_axes` carry "what else is here"). `also_here` SHALL NOT restate a `heading`, an `option` row, or a `refinement_axis`. The tool description SHALL state that `also_here` recovery is a cheap cache-served re-query while `other_pages` each cost a new proxy fetch.

#### Scenario: also_here omitted when the answer covered the page

- **WHEN** the `answer` already relayed all load-bearing on-page content for the question
- **THEN** `also_here` is absent from the wire

#### Scenario: also_here defers to options on a listing

- **WHEN** `query` returns a `listing` whose rows are carried in `options`
- **THEN** `also_here` does not restate those rows and stays sparse

### Requirement: other_pages unifies next_links and try_url

The `AskResponse` envelope SHALL carry a single `other_pages` field (replacing both `next_links` and `try_url`) — a list of `OtherPage` entries `{url, reason, kind, off_domain}` where `kind` is `"structural"` (deterministic continuation: pagination, handler-known links, page-order) or `"drilldown"` (question-conditioned: why this URL answers the gap). `kind` SHALL be `"drilldown"` iff the link's selection depends on the question, else `"structural"`. `other_pages` SHALL render as a TSV block and be omitted when empty. Every `url` SHALL remain page-grounded per ADR-0014 (a rehydrated `{{n}}` closed-set handle or literally on the page); `off_domain` SHALL be carried per ADR-0014 (omitted when False); a `drilldown` `reason` SHALL be question-conditioned (≤120 chars).

#### Scenario: next_links and try_url no longer appear

- **WHEN** any `query` invocation completes
- **THEN** the wire carries no `next_links` and no `try_url` key — continuation and drilldown links appear only under `other_pages` with the appropriate `kind`

#### Scenario: kind discriminates structural from drilldown

- **WHEN** a page exposes both a pagination link and a question-relevant drilldown link
- **THEN** the pagination link is `kind=structural` and the drilldown link is `kind=drilldown` with a question-conditioned `reason`

#### Scenario: URL grounding preserved

- **WHEN** an `other_pages` entry is emitted
- **THEN** its `url` is traceable to the fetched page (rehydrated `{{n}}` handle or literally present) and an off-domain target carries `off_domain=true`

### Requirement: Follow-up suggestions render as queries

`also_here` entries SHALL be emitted as **queries**, defined by deletion: the verb frame and the already-known page entity SHALL be dropped; the target noun(s) and the single discriminating operator SHALL be kept. Permitted operators are free-prior only — `,` (list), `vs` (contrast), `/` (alternatives), quotes (exact), `-` (exclude) — plus CAPS on at most one load-bearing token. A trailing `?` SHALL appear only for a DECIDE (judge/determine-which) entry, not a FIND (retrieve) entry. An entry that would require `and` SHALL be split into two entries.

#### Scenario: a fork survives as a query

- **WHEN** a same-page index entry discriminates between two poles
- **THEN** it keeps the `vs` operator and drops the verb frame — e.g. `connection issues: Apple Home only vs all platforms`

#### Scenario: a compound is split

- **WHEN** an entry would join two distinct asks with `and`
- **THEN** it is emitted as two separate `also_here` entries
