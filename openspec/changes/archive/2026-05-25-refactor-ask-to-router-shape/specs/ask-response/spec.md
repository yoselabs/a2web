## ADDED Requirements

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

## REMOVED Requirements

### Requirement: AskResponse carries an opt-out affordances field by default
**Reason**: Superseded by `AskResponse carries router-shape fields by default`. The single `affordances` payload is replaced by seven explicit fields; the `include_affordances` kwarg is renamed `include_routing`.
**Migration**: Callers using `include_affordances=True/False` MUST migrate to `include_routing=True/False`. Callers reading `AskResponse.affordances.page_kind` MUST read `AskResponse.structural_form` + `AskResponse.genre` + `AskResponse.obstacle`. Callers reading `AskResponse.affordances.shapes[].label` MUST read the singular `AskResponse.shape` (multi-pick collapsed to primary). Callers reading `AskResponse.affordances.follow_up_questions` MUST read `AskResponse.ask_here`. Callers reading `AskResponse.affordances.content_value` or `AskResponse.affordances.page_kind_confidence` MUST treat absence as the same signal — `ask_here` populated ≈ content has more questions to ask, `obstacle` populated ≈ obstacle page, presence of `try_url` ≈ model thinks elsewhere is better.

### Requirement: AffordancesPayload uses closed enums for page_kind, confidence, content_value, and shape labels
**Reason**: The 29-value `page_kind` enum is replaced by three orthogonal axes (`structural_form` 9 values + `genre` 7 values + `obstacle` 4 values), eliminating synonym drift. `page_kind_confidence` and `content_value` are removed; the `AffordanceShape.label` list collapses to the singular `shape` field with 7 values (including new `discussion`).
**Migration**: Closed-enum violations now reject the `RouterPayload` at the boundary; same fail-open behavior as v0.20 (the rest of `AskResponse` is unaffected). The 8-value shape vocabulary (`list, timeline, key-value, table, code, comments, citations, comparison`) is replaced by the 7-value shape vocabulary (`prose, records, key-value, code, table, discussion, mixed`) — callers reading shape labels SHOULD remap (`list` ≈ `records`; `comments` ≈ `discussion`; `comparison` and `citations` fold into `mixed`).

### Requirement: Envelope discipline omits content_value, shapes, and follow_up_questions on obstacle pages
**Reason**: `content_value`, `shapes`, and `follow_up_questions` are removed wholesale; the new conditional fields (`genre`, `obstacle`, `ask_here`, `try_url`) carry their own omit-empty discipline via `_prune_wire`. Obstacle signaling moves to the dedicated `obstacle` field rather than being inferred from `page_kind`.
**Migration**: Callers checking `affordances.page_kind in {"paywalled","error","empty","blocked"}` MUST check `AskResponse.obstacle is not None`. The "omit on obstacle" semantics for inline extractive fields no longer apply because those fields don't exist; obstacle pages simply populate `obstacle` and typically `try_url` (archive fallback).
