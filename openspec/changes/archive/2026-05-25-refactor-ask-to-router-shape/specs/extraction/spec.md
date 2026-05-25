## ADDED Requirements

### Requirement: Extractor supports an opt-in request_routing mode

`Extractor.extract` SHALL accept a `request_routing: bool = False` keyword argument. When `True`, the extractor SHALL use the `EXTRACT_ROUTER_V1` template (instead of the default `EXTRACT_CACHEABLE_V1`), append the router-shape JSON schema to `parts.tail` (NEVER to `parts.cache_prefix`), parse the structured JSON addendum from the model response, and populate `ExtractionResult.routing: RouterPayload | None`.

When `request_routing=False`, `ExtractionResult.routing` SHALL be `None` and the existing `EXTRACT_CACHEABLE_V1` template path SHALL be used with no behavioral change.

The `EXTRACT_ROUTER_V1` template SHALL share `cache_prefix_template` byte-equality with `EXTRACT_CACHEABLE_V1` so the cache-prefix discipline survives — the two prompts differ only in their `tail_template`.

The router-shape tail prompt SHALL:
- Declare the closed-enum vocabulary for `structural_form` (9 values), `shape` (7 values), `genre` (7 values, optional), and `obstacle` (4 values, optional).
- Instruct the model to omit `genre` when no value clearly applies.
- Instruct the model to omit `obstacle` on healthy pages.
- Instruct the model to emit `ask_here` and `try_url` only when populated — empty arrays acceptable but soft-discouraged via a "context decides count, 3 good 5 great" rule.
- Instruct the model that `ask_here` MUST emit only questions whose answer requires reading the body (no obvious-from-title questions).
- Instruct the model that `try_url[*].reason` MUST be question-conditioned (WHY this URL likely has what's missing) and ≤120 chars.

#### Scenario: request_routing=False preserves existing extraction shape

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=False)` is awaited
- **THEN** the model receives the existing `EXTRACT_CACHEABLE_V1` prompt and `ExtractionResult.routing` is `None`

#### Scenario: request_routing=True populates the routing field

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=True)` is awaited against a content page and the model returns a well-formed JSON router-shape addendum
- **THEN** `ExtractionResult.routing` is a `RouterPayload` instance with `answer`, `structural_form`, `shape` populated, plus any of `genre` / `obstacle` / `ask_here` / `try_url` that the model included

#### Scenario: Cache-prefix integrity survives the new template

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` is called for any `X` and any `Y1`, `Y2`
- **THEN** the resulting `PromptParts.cache_prefix` is byte-identical for `(X, Y1)` and `(X, Y2)` — the per-call variation lives entirely in `tail`

#### Scenario: Cache-prefix byte-identical to EXTRACT_CACHEABLE_V1

- **WHEN** both `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` and `EXTRACT_CACHEABLE_V1.render(content=X, ask=Y)` are called
- **THEN** their `cache_prefix` strings are byte-identical (assertable via `test_prompt_cache_stability.py`)

### Requirement: RouterPayload boundary type lives in packages/llm_extract

`RouterPayload` SHALL be a frozen dataclass with `slots=True` declared in `src/a2web/packages/llm_extract/router_payload.py`. It SHALL carry these fields:

- `answer: str`
- `structural_form: str` (string at the package boundary; the pydantic mirror enforces the 9-value closed enum at the domain seam)
- `shape: str` (string at the package boundary; the pydantic mirror enforces the 7-value closed enum)
- `genre: str | None` (optional, `None` when none applies)
- `obstacle: str | None` (optional, `None` on healthy pages)
- `ask_here: tuple[str, ...]` (empty tuple by default)
- `try_url: tuple[NextUrlBoundary, ...]` (empty tuple by default)

`NextUrlBoundary` SHALL be a frozen dataclass carrying `url: str` and `reason: str`.

The module SHALL NOT import from `a2web.<domain>` (enforced by `tests/test_packages_independence.py`). Boundary-to-pydantic projection happens at the domain seam in `src/a2web/fetcher_response.py`.

#### Scenario: RouterPayload is frozen dataclass with slots

- **WHEN** an instance is constructed
- **THEN** the instance has `__slots__`, is `frozen=True`, and attempting to mutate any field raises `dataclasses.FrozenInstanceError`

#### Scenario: Package independence preserved

- **WHEN** `tests/test_packages_independence.py` walks `src/a2web/packages/llm_extract/router_payload.py`
- **THEN** zero imports from `a2web.<domain>` modules are detected

### Requirement: Router-shape parsing tolerates malformed JSON and omitted optional fields

The `Extractor` SHALL parse the router-shape JSON from the model response using a fence-tolerant parser (accepting raw JSON or `\`\`\`json` fenced blocks). When parsing fails, `ExtractionResult.routing` SHALL be `None`, an operator-relevant log message SHALL be emitted, and the extraction call SHALL otherwise succeed (`answer` SHALL still be returned via the existing extraction path).

When the parsed payload omits any of the optional fields (`genre`, `obstacle`, `ask_here`, `try_url`), the boundary type SHALL accept the omission (defaults to `None` for `genre` and `obstacle`; empty tuples for `ask_here` and `try_url`).

When the parsed payload contains an `obstacle` value, the model SHOULD still populate `structural_form` and `shape` with best-guess values; if the model omits them on an obstacle page, the boundary parser SHALL leave `ExtractionResult.routing` as `None` (the obstacle is recorded via the standard fetch-failure path instead).

#### Scenario: Malformed JSON leaves routing None

- **WHEN** the extractor receives a model response with malformed JSON in the router-shape block
- **THEN** `ExtractionResult.routing` is `None` and `ExtractionResult.answer` still carries the successfully parsed answer text

#### Scenario: Healthy page with no obstacle or follow-ups omits all four optionals

- **WHEN** the model returns a router-shape payload with `genre`, `obstacle`, `ask_here`, `try_url` all absent
- **THEN** the boundary type constructs successfully with `genre=None`, `obstacle=None`, `ask_here=()`, `try_url=()`

### Requirement: Claude Code provider isolates MCP servers, subagents, and surfaces num_turns

The `ClaudeCodeProvider` SHALL pass `mcp_servers={}`, `strict_mcp_config=True`, and `agents={}` to `ClaudeAgentOptions` in addition to the existing `setting_sources=[]`, `skills=[]`, and `extra_args={"disable-slash-commands": None}` opt-outs. This SHALL prevent the host Claude Code CLI's MCP server config (including memory-bearing MCP servers) from contaminating the extraction call.

The provider SHALL surface `num_turns` from `ResultMessage.raw` so callers can verify the `max_turns=1` cap held in production.

#### Scenario: MCP servers and subagents are explicitly disabled

- **WHEN** `ClaudeCodeProvider.complete` is awaited
- **THEN** the `ClaudeAgentOptions` instance has `mcp_servers={}`, `strict_mcp_config=True`, and `agents={}` set, regardless of the host CLI's MCP config

#### Scenario: num_turns surfaces in the response raw blob

- **WHEN** `ClaudeCodeProvider.complete` returns
- **THEN** `ProviderResponse.raw["num_turns"]` is present and equals 1 (matching the `max_turns=1` cap)

## REMOVED Requirements

### Requirement: Extractor supports an opt-in request_affordances mode
**Reason**: Superseded by `Extractor supports an opt-in request_routing mode`. The v0.20 `request_affordances` kwarg and `EXTRACT_WITH_AFFORDANCES_V1` template are replaced wholesale by `request_routing` and `EXTRACT_ROUTER_V1`. No coexistence path.
**Migration**: Callers using `Extractor.extract(request_affordances=True)` MUST migrate to `Extractor.extract(request_routing=True)`. The `ExtractionResult.affordances` field is replaced by `ExtractionResult.routing`. Cache-prefix byte-equality with `EXTRACT_CACHEABLE_V1` invariant carries forward unchanged.

### Requirement: AffordancesPayload boundary type lives in packages/llm_extract
**Reason**: Replaced by `RouterPayload` boundary type with the seven router-shape fields (3 required + 4 optional). The old field set (`page_kind`, `page_kind_confidence`, `content_value`, `shapes`, `follow_up_questions`, `reasoning`) is fully retired.
**Migration**: Callers reading `AffordancesPayload.page_kind` MUST split into `RouterPayload.structural_form` + `RouterPayload.genre` + `RouterPayload.obstacle`. `content_value` and `page_kind_confidence` callers MUST treat absence as the equivalent signal (presence of `ask_here` / `try_url` ≈ content_value; absence of `obstacle` ≈ confident healthy page). `AffordanceShape.label` callers MUST read the singular `RouterPayload.shape`. `AffordancesPayload.follow_up_questions` callers MUST read `RouterPayload.ask_here`. File `packages/llm_extract/affordances.py` is replaced by `packages/llm_extract/router_payload.py`.

### Requirement: Affordances parsing tolerates malformed JSON and obstacle-page omissions
**Reason**: Replaced by `Router-shape parsing tolerates malformed JSON and omitted optional fields`. The omit-empty semantics shift from "obstacle pages omit content_value/shapes/follow_ups" to "any page omits any of four optional fields when not populated" — a more general discipline matching `_prune_wire`.
**Migration**: Parser callers expecting `affordances=None` on obstacle remains unchanged in spirit — obstacle pages now populate `RouterPayload.obstacle` and typically `try_url`, with `structural_form` / `shape` still required.

### Requirement: G_commerce cluster trigger forces medium confidence on commerce/listing ambiguity
**Reason**: The tighter 9-value `structural_form` enum eliminates the synonym pairs that motivated cluster rules A-G. `product` and `listing` are now structurally distinct (single-offering page vs feed-of-items); `page_kind_confidence` itself is removed.
**Migration**: Consumers relying on `page_kind_confidence in {"low","medium"}` on commerce pages MUST instead branch on `structural_form in {"product", "listing"}` directly — the structural enum's clearer boundaries make confidence-rating unnecessary for this case.
