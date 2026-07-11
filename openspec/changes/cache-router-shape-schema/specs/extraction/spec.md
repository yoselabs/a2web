## MODIFIED Requirements

### Requirement: Extractor supports an opt-in request_routing mode

`Extractor.extract` SHALL accept a `request_routing: bool = False` keyword argument. When `True`, the extractor SHALL use the `EXTRACT_ROUTER_V1` template (instead of the default `EXTRACT_CACHEABLE_V1`), append the router-shape JSON schema documentation and worked examples to `parts.system` (NEVER to `parts.cache_prefix`), parse the structured JSON addendum from the model response, and populate `ExtractionResult.routing: RouterPayload | None`. Only the per-call question (`"Question: {ask}"`) lives in `parts.tail` — the schema/examples text is static (independent of `content` and `ask`) and therefore lives in the cacheable `system` bucket alongside the general instructions, not in the always-resent `tail`.

When `request_routing=False`, `ExtractionResult.routing` SHALL be `None` and the existing `EXTRACT_CACHEABLE_V1` template path SHALL be used with no behavioral change.

The `EXTRACT_ROUTER_V1` template SHALL share `cache_prefix_template` byte-equality with `EXTRACT_CACHEABLE_V1` so the cache-prefix discipline survives — the two prompts differ only in `system` and `tail_template`.

The router-shape system prompt SHALL:
- Declare the closed-enum vocabulary for `structural_form` (9 values), `shape` (7 values), and `obstacle` (4 values, optional).
- Instruct the model to omit `obstacle` on healthy pages.
- Instruct the model to emit `ask_here` and `try_url` only when populated — empty arrays acceptable but soft-discouraged via a "context decides count, 3 good 5 great" rule.
- Instruct the model that `ask_here` MUST emit only questions whose answer requires reading the body (no obvious-from-title questions).
- Instruct the model that `try_url[*].reason` MUST be question-conditioned (WHY this URL likely has what's missing) and ≤120 chars.

#### Scenario: request_routing=False preserves existing extraction shape

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=False)` is awaited
- **THEN** the model receives the existing `EXTRACT_CACHEABLE_V1` prompt and `ExtractionResult.routing` is `None`

#### Scenario: request_routing=True populates the routing field

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=True)` is awaited against a content page and the model returns a well-formed JSON router-shape addendum
- **THEN** `ExtractionResult.routing` is a `RouterPayload` instance with `answer`, `structural_form`, `shape` populated, plus any of `obstacle` / `ask_here` / `try_url` that the model included

#### Scenario: Cache-prefix integrity survives the new template

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` is called for any `X` and any `Y1`, `Y2`
- **THEN** the resulting `PromptParts.cache_prefix` is byte-identical for `(X, Y1)` and `(X, Y2)` — the per-call variation lives entirely in `tail`

#### Scenario: Cache-prefix byte-identical to EXTRACT_CACHEABLE_V1

- **WHEN** both `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` and `EXTRACT_CACHEABLE_V1.render(content=X, ask=Y)` are called
- **THEN** their `cache_prefix` strings are byte-identical (assertable via `test_prompt_cache_stability.py`)

#### Scenario: Router-shape schema and examples are cacheable, not resent per call

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y1)` and `EXTRACT_ROUTER_V1.render(content=X, ask=Y2)` are called for two different questions `Y1`, `Y2` over the same `X`
- **THEN** `system` is byte-identical across both calls (it contains the full schema documentation and worked examples), and `tail` differs only in the embedded question text — the schema/examples are never part of the per-call `tail` payload
