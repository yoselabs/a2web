# ask-response Specification

## Purpose
TBD - created by archiving change ask-response-diet. Update Purpose after archive.
## Requirements
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

### Requirement: AskResponse meta is curated to an allowlist

`AskResponse.meta` SHALL be populated from a curated allowlist of the raw metadata dict — `og.description` only — not a verbatim copy of every key `parse_metadata` produces. `og.title` SHALL NOT appear in the allowlist — it duplicates the already-promoted top-level `title` field (same source, same string). `og.site_name` SHALL NOT appear in the allowlist either — a live sweep of 6 real pages (design D6) found it always equal to the obvious human-readable form of the domain already present in the requested URL, carrying no incremental signal. Keys outside the allowlist (e.g. `og.title`, `og.site_name`, `og.locale`, `og.image`, `og.image:width`, `og.image:height`, `og.image:type`, `og.type`, `og.url`, `twitter.card`, `twitter.creator`, `twitter.site`, `twitter.title`, `twitter.description`, `twitter.label1`/`data1`, `twitter.label2`/`data2`, `jsonld[0].@context`, `jsonld[0].name`, `jsonld[0].url`) SHALL NOT appear on the `ask` wire. `FetchResponse.meta` (the `fetch_raw` envelope) SHALL remain the full, uncurated dict — this requirement applies only to the `AskResponse` projection.

This requirement governs only the shallow `og:*`/`twitter:*`/`jsonld[0].*` scalar flatten `parse_metadata` produces — it is out of scope for (and does not gatekeep) structured facts like a phone number or address, since the shelf's `_flatten_jsonld` already drops nested JSON-LD objects before this allowlist ever runs (design D7). Such facts, when present, are surfaced through a different pipeline entirely — the extraction escalation ladder's entity renderer (`extraction` capability, "JSON-LD single-entity rendering is default-keep") — which this requirement does not modify.

#### Scenario: ask curates meta to the allowlist

- **WHEN** `ask` completes against a fixture whose raw metadata carries `og.title`, `og.description`, `og.site_name`, `og.image`, `og.image:width`, `twitter.card`, `twitter.label1`, and `jsonld[0].@context`
- **THEN** the `ask` wire payload's `meta` object contains `og.description` and omits `og.title`, `og.site_name`, `og.image`, `og.image:width`, `twitter.card`, `twitter.label1`, and `jsonld[0].@context`

#### Scenario: fetch_raw keeps the full raw metadata

- **WHEN** `fetch_raw` completes against the same fixture
- **THEN** the `fetch_raw` wire payload's `meta` object contains every key `parse_metadata` produced, uncurated

#### Scenario: empty allowlisted meta is still omitted

- **WHEN** `ask` completes against a fixture whose raw metadata carries only non-allowlisted keys
- **THEN** the `ask` wire payload contains no `meta` key

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

### Requirement: RouterPayload uses closed enums on every typed field

The `RouterPayload` pydantic model SHALL declare each typing field as a typed `Literal`:

- `structural_form` — `Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]` (9 values, required).
- `shape` — `Literal["prose","records","key-value","code","table","discussion","mixed"]` (7 values, required).
- `obstacle` — `Literal["paywalled","blocked","empty","error"] | None` (4 values, optional).

`RouterPayload` SHALL NOT declare a `genre` field. `NextUrl.url` SHALL be a string. `NextUrl.reason` SHALL be a string. Values outside the closed enums SHALL be rejected by pydantic validation at the model boundary, and the boundary projection SHALL leave the six router-shape fields absent on validation failure (the answer text on `AskResponse.answer` is unaffected).

#### Scenario: Closed structural_form rejects unknown values

- **WHEN** an extractor response carries `structural_form: "blog-post"` (a v0.20-era label not in the new enum)
- **THEN** the boundary projection raises a pydantic validation error, all six router-shape fields are absent from `AskResponse`, and `answer` carries the extractor's answer text unchanged

#### Scenario: Closed shape rejects unknown values

- **WHEN** an extractor response carries `shape: "diagram"`
- **THEN** the boundary projection raises a pydantic validation error and the six router-shape fields are absent

#### Scenario: Optional obstacle field accepts None

- **WHEN** an extractor response carries no `obstacle` key
- **THEN** `RouterPayload.obstacle` resolves to `None` and is absent from the wire

#### Scenario: A stray genre key from a non-conforming extractor response is ignored

- **WHEN** an extractor response carries a `genre` key (e.g. from a stale prompt version or a non-conforming provider)
- **THEN** `RouterPayload` parses successfully ignoring the extra key, and no `genre` key reaches the `AskResponse` wire

### Requirement: Router-shape envelope omits empty conditional fields via _prune_wire

The `AskResponse._prune_wire` serializer SHALL treat the three conditional router-shape fields as omit-empty:

- `obstacle` is omitted when `None`.
- `ask_here` is omitted when `[]`.
- `try_url` is omitted when `[]`.

The one required field (`answer`) SHALL always appear when present on the model. No `genre`, `structural_form`, or `shape` field exists on `AskResponse` to prune.

#### Scenario: Healthy article with complete answer omits all three conditionals

- **WHEN** `ask` returns a routing payload with `obstacle=None`, `ask_here=[]`, `try_url=[]`
- **THEN** the wire payload contains `answer` plus the rest of the AskResponse envelope; no `genre`, `structural_form`, `shape`, `obstacle`, `ask_here`, or `try_url` keys

#### Scenario: Obstacle page populates obstacle and try_url

- **WHEN** `ask` returns a routing payload with `obstacle="paywalled"` and `try_url=[{...}]`
- **THEN** the wire contains both keys, plus `answer`, with `ask_here` omitted if not populated, and no `genre`, `structural_form`, or `shape` key under any circumstance

#### Scenario: Field shape survives the formatter wire path

- **WHEN** `ask` with the router-shape is invoked through the in-process test client (production formatter wrapper chain)
- **THEN** the marshaled result has omit-empty conditionals absent (not present as `null` or `[]`), and no `genre`, `structural_form`, or `shape` key

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

### Requirement: Ask envelope carries dimensional refinement axes on a partial listing

The `AskResponse` envelope SHALL carry a conditional `refinement_axes` field on a partial listing,
listing the dimensions to re-query on (per the `refinement-guidance` capability). Each axis SHALL
name a dimension and how to apply it, and SHALL NOT be a specific item value drawn from the biased
sample. The field SHALL be treated as omit-empty by `_prune_wire` — absent from the wire when there
are no axes (a complete listing, or a non-listing page). The field is additive and conditional; it
does not change existing required or debug fields, and it does not alter the tool signature.

#### Scenario: Partial listing surfaces refinement axes

- **WHEN** an `ask` fetch returns a partial listing and the extractor produced refinement axes
- **THEN** the wire payload includes `refinement_axes` as a list of dimensional axes, each naming a dimension and how to apply it

#### Scenario: Complete or non-listing response omits the field

- **WHEN** an `ask` fetch returns a complete listing or a non-listing page (no axes produced)
- **THEN** `refinement_axes` is absent from the wire (not present as `null` or `[]`)

#### Scenario: Axes carry no sample-derived values

- **WHEN** refinement axes are emitted for a price-sorted, truncated listing
- **THEN** each axis names a dimension (e.g. "narrow by brand", "add a price floor") and none recommends a specific item or value taken from the retrieved sample

### Requirement: ask retains the parsed listing options (rank, don't skip)

On a listing-selection question, the `ask` envelope SHALL carry a conditional
`options` list projected from the parsed listing records — one entry per parsed
record, each naming the record's title, url, and its own detail text (carrying
price / rating as extracted). The `answer` MAY still crown a ranked top pick; the
`options` list SHALL preserve the parsed page order and SHALL NOT be re-ranked by
a2web, so a lower-ranked or unrated item (e.g. a premium/niche option) remains
visible rather than deleted. The field SHALL be populated iff the record detector
produced a record set for the page, SHALL be absent from the wire on non-listing
pages (no record set), and SHALL be treated as omit-empty by `_prune_wire`. The
list carries the parsed (fetched) records only and does NOT assert completeness —
the `listing_partial` / `listing_more` signals still own the completeness axis.

#### Scenario: Listing ask carries the option set alongside the ranked answer

- **WHEN** an `ask` fetch returns a listing whose record detector parsed N records
- **THEN** the wire carries `options` as a list of N entries, each with a title, url, and detail
- **AND** `answer` may name a top pick, but every parsed record is present in `options`, in page order

#### Scenario: Options are not re-ranked by a2web

- **WHEN** an `ask` fetch over a price-sorted listing returns an `options` list
- **THEN** the `options` preserve the page order (a2web does not reorder them by rating or price)
- **AND** any ranking is expressed only in `answer`, not by the position of items in `options`

#### Scenario: Non-listing ask omits the field

- **WHEN** an `ask` fetch returns an article or single entity (no record set parsed)
- **THEN** `options` is absent from the wire (not present as `null` or `[]`)

#### Scenario: Empty option set is omitted

- **WHEN** a listing parse yields no usable records
- **THEN** `options` is absent from the wire

### Requirement: ask is neutral on selection questions

The `ask` answer SHALL NOT assert a2web's own unqualified "best" on a question
that asks a2web to pick from a set (a which/best/compare question over a listing
or option set). It MAY offer a criterion-disclosed lead (naming the criterion and
framing it as one lens, e.g. "by rating, X leads"), and it SHALL relay any
source-stated preference attributed to the page (e.g. "the site marks X as
preferred"), never as a2web's own judgment. The answer SHALL present the option
space rather than decide it, and SHALL remain exhaustive (it MUST NOT decline and
under-deliver in the same breath). Single-fact questions (e.g. asking for a phone
number) are out of scope and answer as before.

#### Scenario: Selection question offers a criterion-disclosed lead, not a verdict

- **WHEN** an `ask` fetch answers a "which is best?" question over a listing
- **THEN** the answer does not assert an unqualified "best"
- **AND** any lead it offers names the criterion and frames it as one lens, not the answer

#### Scenario: Source-stated preference is relayed, attributed

- **WHEN** the fetched page marks its own preference (e.g. a contact page tags one channel "preferred")
- **THEN** the answer surfaces that preference as the source's ("the site marks X as preferred")
- **AND** the answer does not present it as a2web's own recommendation

#### Scenario: Neutral is not lazy

- **WHEN** the answer declines to crown a single best
- **THEN** it still presents the option space (and relays source preference / criteria) in the same response
- **AND** does not force the caller to re-ask the same page to recover data already on it

#### Scenario: Single-fact question is unaffected

- **WHEN** an `ask` fetch answers a single-fact question (not a selection over a set)
- **THEN** the answer behaviour is unchanged (lean, direct)

### Requirement: criteria surface on any listing selection, not only partial ones

`refinement_axes` (the judgable dimensions of the option set) SHALL be surfaced on
any listing selection question, decoupled from the completeness signal — not gated
on the listing being partial. Criteria and partialness are orthogonal: a complete
listing still needs its criteria surfaced for a "best?" question. The field remains
additive and omit-empty (absent when there are no axes or the page is not a listing).

#### Scenario: Complete listing still surfaces criteria

- **WHEN** an `ask` fetch returns a complete listing (no `listing_partial` signal) for a selection question
- **THEN** `refinement_axes` may still be present (gated on the listing kind, not on partialness)

#### Scenario: Non-listing omits criteria

- **WHEN** an `ask` fetch returns a non-listing page
- **THEN** `refinement_axes` is absent from the wire

### Requirement: try_url URLs are rehydrated, never model-typed

`try_url` entries SHALL carry hrefs rehydrated from the closed digest set (owned by `link-affordances`), not URLs typed by the extractor. An entry whose handle is absent from the digest SHALL NOT appear. The prior "URL must appear verbatim in content" instruction is superseded: the model references a handle, and the server supplies the real URL.

#### Scenario: try_url carries a real anchor href

- **WHEN** the extractor selects handle `{{3}}` for a drilldown
- **THEN** the `try_url` entry's URL is the real href for handle 3

#### Scenario: Hallucinated URL cannot appear

- **WHEN** the extractor emits a handle not in the digest
- **THEN** no corresponding `try_url` entry is produced

### Requirement: try_url entries flag off-domain targets

Each `try_url` entry SHALL indicate whether its target is off the fetched page's domain, so the caller can treat off-domain suggestions (whose anchor labels are attacker-controllable) with appropriate caution.

#### Scenario: Off-domain flag present

- **WHEN** a `try_url` target is on a different registrable domain than the fetched page
- **THEN** the entry is marked off-domain on the wire

### Requirement: Continuation link promoted on incomplete answers

When the answer is incomplete and a continuation link exists, that link SHALL be surfaced with top priority (first, or in a dedicated continuation position) rather than buried among speculative drilldowns, consistent with the retrieval-completeness invariant.

#### Scenario: Reviews continuation ranked first

- **WHEN** a product page cannot answer a reviews question but links the reviews page
- **THEN** the reviews link is the top-priority `try_url` entry

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

