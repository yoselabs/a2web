## ADDED Requirements

### Requirement: Extractor supports an opt-in request_affordances mode

`Extractor.extract` SHALL accept a `request_affordances: bool = False` keyword argument. When `True`, the extractor SHALL use the `EXTRACT_WITH_AFFORDANCES_V1` template (instead of the default `EXTRACT_CACHEABLE_V1`), append the affordances request schema to `parts.tail` (NEVER to `parts.cache_prefix`), parse the structured JSON addendum from the model response, and populate `ExtractionResult.affordances: AffordancesPayload | None`.

When `request_affordances=False` (the existing default for callers that don't opt in), `ExtractionResult.affordances` SHALL be `None` and the existing `EXTRACT_CACHEABLE_V1` template path SHALL be used with no behavioral change.

The `EXTRACT_WITH_AFFORDANCES_V1` template SHALL share `cache_prefix_template` byte-equality with `EXTRACT_CACHEABLE_V1` so the cache-prefix discipline survives — the prompts differ only in their `tail_template` (which already carries per-call variation in the existing design).

#### Scenario: request_affordances=False preserves existing extraction shape

- **WHEN** `Extractor.extract(content=..., ask=..., request_affordances=False)` is awaited
- **THEN** the model receives the existing `EXTRACT_CACHEABLE_V1` prompt and `ExtractionResult.affordances` is `None`

#### Scenario: request_affordances=True populates the affordances field

- **WHEN** `Extractor.extract(content=..., ask=..., request_affordances=True)` is awaited against a content page and the model returns a well-formed JSON affordances addendum
- **THEN** `ExtractionResult.affordances` is an `AffordancesPayload` instance with `page_kind`, `page_kind_confidence`, `reasoning`, `content_value`, `shapes`, and `follow_up_questions` populated

#### Scenario: Cache-prefix integrity survives the new template

- **WHEN** `EXTRACT_WITH_AFFORDANCES_V1.render(content=X, ask=Y)` is called for any `X` and any `Y1`, `Y2`
- **THEN** the resulting `PromptParts.cache_prefix` is byte-identical for `(X, Y1)` and `(X, Y2)` — the per-call variation lives entirely in `tail`

### Requirement: AffordancesPayload boundary type lives in packages/llm_extract

`AffordancesPayload` SHALL be a frozen dataclass with `slots=True` declared in `src/a2web/packages/llm_extract/affordances.py`. It SHALL carry these fields:

- `page_kind: str` (string at the package boundary; the pydantic mirror enforces the closed enum at the domain seam)
- `page_kind_confidence: str` (low | medium | high)
- `reasoning: str`
- `content_value: str | None` (low | medium | high; `None` when `page_kind` is an obstacle kind)
- `shapes: tuple[AffordanceShape, ...]` (empty tuple when obstacle)
- `follow_up_questions: tuple[str, ...]` (empty tuple when obstacle)

`AffordanceShape` SHALL be a frozen dataclass carrying `label: str`, `where: str`, `size: str`.

The module SHALL NOT import from `a2web.<domain>` (enforced by `tests/test_packages_independence.py`). Boundary-to-pydantic projection happens at the domain seam in `src/a2web/fetcher_response.py`.

#### Scenario: AffordancesPayload is frozen dataclass with slots

- **WHEN** an instance is constructed
- **THEN** the instance has `__slots__`, is `frozen=True`, and attempting to mutate any field raises `dataclasses.FrozenInstanceError`

#### Scenario: Package independence preserved

- **WHEN** `tests/test_packages_independence.py` walks `src/a2web/packages/llm_extract/affordances.py`
- **THEN** zero imports from `a2web.<domain>` modules are detected

### Requirement: Affordances parsing tolerates malformed JSON and obstacle-page omissions

The `Extractor` SHALL parse the affordances JSON addendum from the model response using a fence-tolerant parser (accepting raw JSON or `\`\`\`json` fenced blocks). When parsing fails, `ExtractionResult.affordances` SHALL be `None`, an operator-relevant log message SHALL be emitted, and the extraction call SHALL otherwise succeed (the `answer` field SHALL still be returned).

When the parsed payload has `page_kind` in the obstacle set (`paywalled`, `error`, `empty`, `blocked`) and `content_value` / `shapes` / `follow_up_questions` are absent or empty, the boundary type SHALL accept the omission (defaults to `None` for `content_value`, empty tuples for shapes/follow_ups).

#### Scenario: Malformed JSON leaves affordances None

- **WHEN** the extractor receives a model response with malformed JSON in the affordances block
- **THEN** `ExtractionResult.affordances` is `None` and `ExtractionResult.answer` still carries the successfully parsed answer text

#### Scenario: Obstacle page payload omits content_value cleanly

- **WHEN** the model returns an affordances payload with `page_kind="error"` and no `content_value` / `shapes` / `follow_up_questions` keys
- **THEN** the boundary type constructs successfully with `content_value=None`, `shapes=()`, `follow_up_questions=()`

### Requirement: G_commerce cluster trigger forces medium confidence on commerce/listing ambiguity

The `EXTRACT_WITH_AFFORDANCES_V1` prompt SHALL declare 7 confusable-label clusters in its `tail_template`: A_academic, B_landing, C_dashboard, D_changelog, E_feed, F_longform, and **G_commerce: {listing, product-page, package-page}**. The G_commerce cluster fixes the v5 spike's Amazon-style miscalibration where `product-amazon` was classified as `listing` with `high` confidence.

The prompt SHALL instruct the model that any `page_kind` falling in a cluster MUST set `page_kind_confidence` to `low` or `medium`, never `high`.

#### Scenario: Commerce/listing confusion forces medium confidence

- **WHEN** `Extractor.extract` runs `EXTRACT_WITH_AFFORDANCES_V1` on a product page that the model classifies as `listing` (or `product-page`)
- **THEN** the parsed `page_kind_confidence` is `low` or `medium`, never `high`
