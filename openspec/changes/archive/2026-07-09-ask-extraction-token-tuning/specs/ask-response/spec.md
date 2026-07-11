## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: AskResponse carries router-shape fields by default

`AskResponse` SHALL declare six router-shape fields replacing the v0.20 `affordances` field:

Required fields (always present on the wire when the LLM extractor returned a routing payload):
- `answer: str` — the model's answer to the question.
- `structural_form: Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]` — what the page IS structurally.
- `shape: Literal["prose","records","key-value","code","table","discussion","mixed"]` — the data shape of the answer-bearing content.

Conditional fields (omitted from the wire via `_prune_wire` when empty/null):
- `obstacle: Literal["paywalled","blocked","empty","error"] | None` — page-level failure mode; omitted on healthy pages.
- `ask_here: list[str]` — same-URL re-asks; omitted when `[]`.
- `try_url: list[NextUrl]` — different-URL re-asks where each entry has `{url, reason}`; omitted when `[]`.

`AskResponse` SHALL NOT declare a `genre` field. The extraction prompt SHALL NOT request a `genre` value from the LLM — the audit backing this change found no downstream consumer of `genre` anywhere in the pipeline (unlike `structural_form`, `shape`, and `obstacle`, each of which has a confirmed consumer).

The `ask` tool SHALL accept an `include_routing: bool` parameter defaulting to `True`. When `include_routing=False`, all six fields SHALL be `None` / absent and the wire SHALL carry the lean v0.14 envelope shape. When `include_routing=True` but the extractor returned no routing payload (no LLM, fetch error, parse failure), all six fields SHALL be absent.

#### Scenario: Default ask includes the router-shape fields

- **WHEN** `ask` is called without `include_routing` against a content page that the LLM successfully extracts
- **THEN** the wire carries `answer`, `structural_form`, `shape` always, plus `obstacle` / `ask_here` / `try_url` only when populated, and no `genre` key under any circumstance

#### Scenario: Opt-out via include_routing=False suppresses all six fields

- **WHEN** `ask` is called with `include_routing=False`
- **THEN** the wire carries no `structural_form`, `shape`, `obstacle`, `ask_here`, or `try_url` keys (and `answer` remains the unstructured extractor answer)

#### Scenario: Extractor unavailable leaves router fields absent

- **WHEN** `ask` is called with `include_routing=True` but the LLM extractor is unavailable
- **THEN** the wire carries none of the six router-shape fields, and an `operator_hint` with `code="llm_unavailable"` records the reason

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

The three required fields (`answer`, `structural_form`, `shape`) SHALL always appear when present on the model. No `genre` field exists to prune.

#### Scenario: Healthy article with complete answer omits all three conditionals

- **WHEN** `ask` returns a routing payload with `obstacle=None`, `ask_here=[]`, `try_url=[]`
- **THEN** the wire payload contains exactly `answer`, `structural_form`, `shape`, plus the rest of the AskResponse envelope; no `genre`, `obstacle`, `ask_here`, or `try_url` keys

#### Scenario: Obstacle page populates obstacle and try_url

- **WHEN** `ask` returns a routing payload with `obstacle="paywalled"` and `try_url=[{...}]`
- **THEN** the wire contains both keys, plus `answer`, `structural_form`, `shape`, with `ask_here` omitted if not populated, and no `genre` key under any circumstance

#### Scenario: Field shape survives the formatter wire path

- **WHEN** `ask` with the router-shape is invoked through the in-process test client (production formatter wrapper chain)
- **THEN** the marshaled result has omit-empty conditionals absent (not present as `null` or `[]`), and no `genre` key
