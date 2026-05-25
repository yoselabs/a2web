## ADDED Requirements

### Requirement: AskResponse carries an opt-out affordances field by default

`AskResponse` SHALL declare an `affordances: AffordancesPayload | None` field. The `ask` tool SHALL accept an `include_affordances: bool` parameter defaulting to `True` — consumers decide whether to use the data; a2web's role is to surface it.

When `include_affordances` is `False`, `affordances` SHALL be `None` and the field SHALL be omitted from the wire payload. When `include_affordances` is `True` and the extractor returned an affordances payload, `affordances` SHALL be populated and present on the wire. When `include_affordances` is `True` but the extraction failed (no LLM, fetch error, parse failure), `affordances` SHALL be `None` and the field SHALL be omitted.

#### Scenario: Default ask includes the affordances field

- **WHEN** `ask` is called without `include_affordances` against a content page
- **THEN** the wire payload contains an `affordances` object with `page_kind`, `page_kind_confidence`, `reasoning`, and (for content pages) `content_value`, `shapes`, `follow_up_questions`

#### Scenario: Opt-out via include_affordances=False suppresses the field

- **WHEN** `ask` is called with `include_affordances=False`
- **THEN** the wire payload contains no `affordances` key, and the response carries the lean v0.14 envelope shape

#### Scenario: Extractor unavailable leaves affordances absent

- **WHEN** `ask` is called with `include_affordances=True` but the LLM extractor is unavailable (no API key, no Claude Code session)
- **THEN** the wire payload contains no `affordances` key, and an `operator_hint` with `code="llm_unavailable"` records the reason

### Requirement: AffordancesPayload uses closed enums for page_kind, confidence, content_value, and shape labels

The `AffordancesPayload` pydantic model SHALL declare `page_kind` as a typed `Literal` over exactly these 29 values:

- Content kinds (24): `listing`, `thread`, `reference`, `api-reference`, `tutorial`, `article-short`, `article-long`, `changelog`, `code-snippet`, `source-file`, `readme`, `qa`, `spec`, `filing`, `news-article`, `blog-post`, `product-page`, `video-page`, `json-feed`, `marketing`, `encyclopedia`, `package-page`, `pdf-stub`, `spa`
- Obstacle kinds (4): `paywalled`, `error`, `empty`, `blocked`
- Catch-all (1): `other`

`page_kind_confidence` SHALL be a typed `Literal["low", "medium", "high"]`. `content_value` SHALL be a typed `Literal["low", "medium", "high"] | None`. The `AffordanceShape.label` field SHALL be a typed `Literal` over exactly 8 values: `list`, `timeline`, `key-value`, `table`, `code`, `comments`, `citations`, `comparison`.

Values outside the closed enums SHALL be rejected by pydantic validation at the model boundary.

#### Scenario: Closed page_kind enum rejects unknown values

- **WHEN** an extractor response carries `page_kind: "unknown-shape"`
- **THEN** the boundary projection raises a pydantic validation error and `AskResponse.affordances` is left `None`

#### Scenario: Closed shape label enum rejects unknown values

- **WHEN** an extractor response carries a shape with `label: "diagram"`
- **THEN** the boundary projection raises a pydantic validation error and `AskResponse.affordances` is left `None`

### Requirement: Envelope discipline omits content_value, shapes, and follow_up_questions on obstacle pages

When `AffordancesPayload.page_kind` is an obstacle kind (`paywalled`, `error`, `empty`, `blocked`), the wire payload SHALL omit `content_value`, `shapes`, and `follow_up_questions`. Their absence carries the meaning that there is nothing extractable; `page_kind` already names the obstacle.

When `page_kind` is a content kind or `other`, all three fields SHALL be present on the wire (lists MAY be empty in degenerate cases but the keys SHALL exist).

#### Scenario: Obstacle page omits content_value and friends

- **WHEN** `ask` returns an affordances payload with `page_kind="error"`
- **THEN** the wire `affordances` object contains `page_kind`, `page_kind_confidence`, `reasoning`, `answer` (the obstacle statement), and NO `content_value`, `shapes`, or `follow_up_questions` keys

#### Scenario: Content page carries all affordance fields

- **WHEN** `ask` returns an affordances payload with `page_kind="encyclopedia"`
- **THEN** the wire `affordances` object contains `content_value` ("low" | "medium" | "high"), `shapes` (possibly empty), and `follow_up_questions` (possibly empty)

#### Scenario: Field shape survives the formatter wire path

- **WHEN** `ask` with affordances is invoked through the in-process test client (production formatter wrapper chain)
- **THEN** the marshaled result has obstacle-omitted fields absent, not present as `null`
