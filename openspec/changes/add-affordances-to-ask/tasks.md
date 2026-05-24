## 1. Boundary types in packages/llm_extract

- [x] 1.1 Create `src/a2web/packages/llm_extract/affordances.py` with frozen `@dataclass(slots=True)` `AffordanceShape` (label, where, size — all `str`).
- [x] 1.2 Add `AffordancesPayload` frozen dataclass to the same module: `page_kind: str`, `page_kind_confidence: str`, `reasoning: str`, `content_value: str | None`, `shapes: tuple[AffordanceShape, ...]`, `follow_up_questions: tuple[str, ...]`. All fields default to safe values (empty strings / `None` / empty tuples).
- [x] 1.3 Export `AffordancesPayload` + `AffordanceShape` from `src/a2web/packages/llm_extract/__init__.py`.

## 2. Prompt template

- [x] 2.1 Lift the V_CTX_V3 prompt from `eval/spikes/affordances_v5_two_axes.py` (the `V_CTX_V3_SYSTEM` + `V_CTX_V3_TEMPLATE` constants) into `src/a2web/packages/llm_extract/prompts.py` as `EXTRACT_WITH_AFFORDANCES_V1`.
- [x] 2.2 Confirm `cache_prefix_template` is byte-identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template` (load-bearing — the cache discipline depends on it). Differ only in `tail_template`.
- [x] 2.3 Add `G_commerce: {listing, product-page, package-page}` to the cluster trigger list in the template (pre-ship fix for the v5 Amazon miscalibration).
- [x] 2.4 Add `EXTRACT_WITH_AFFORDANCES_V1` to the module's `__all__`.

## 3. Extractor wiring

- [x] 3.1 Add `request_affordances: bool = False` kwarg to `Extractor.extract`. Select template based on flag (existing `EXTRACT_CACHEABLE_V1` when False; `EXTRACT_WITH_AFFORDANCES_V1` when True). Document the per-call template override (constructor still receives a default template — the flag overrides for the duration of the call).
- [x] 3.2 Add `affordances: AffordancesPayload | None = None` to `ExtractionResult` dataclass.
- [x] 3.3 Write a fence-tolerant JSON parser helper `_parse_affordances_block(text: str) -> AffordancesPayload | None` that handles raw JSON, ```json fences, and obstacle-page partial payloads (defaults `content_value=None`, `shapes=()`, `follow_up_questions=()`).
- [x] 3.4 Wire the parser into the extract path: when `request_affordances=True`, split the model response into answer + affordances block (similar to the existing next_links split), parse, attach to `ExtractionResult.affordances`. On parse failure, log a structlog warning and leave `affordances=None`.
- [x] 3.5 Confirm cache-write path still works on `request_affordances=True` runs (only the answer text gets cached; affordances are not part of the cache key).

## 4. LlmExtractorResource and fetcher plumbing

- [x] 4.1 Add `request_affordances: bool = False` kwarg to `LlmExtractorResource.extract`; pass through to `Extractor.extract`.
- [x] 4.2 Add `include_affordances: bool = True` kwarg to `fetcher.fetch` and thread it through `FetchContext` to the `_phase_extract` phase.
- [x] 4.3 In `_phase_extract`, pass `request_affordances=include_affordances` into the `LlmExtractorResource.extract` call.
- [x] 4.4 Surface the resulting `AffordancesPayload` on a new internal field on `FetchResponse` (NOT the wire — the wire field lives on `AskResponse` only). Choose a private-feeling name like `_affordances` or extend the existing `ExtractionResult` shape exposed internally.

## 5. Domain-side pydantic mirrors

- [x] 5.1 In `src/a2web/models.py`, add a `PageKind` typed `Literal` covering the 29 values from the spec (24 content + 4 obstacle + `other`).
- [x] 5.2 Add `ShapeLabel = Literal["list","timeline","key-value","table","code","comments","citations","comparison"]`.
- [x] 5.3 Add pydantic `AffordanceShape` model with `label: ShapeLabel`, `where: str`, `size: str`.
- [x] 5.4 Add pydantic `AffordancesPayload` model: `page_kind: PageKind`, `page_kind_confidence: Literal["low","medium","high"]`, `reasoning: str`, `content_value: Literal["low","medium","high"] | None = None`, `shapes: list[AffordanceShape] = []`, `follow_up_questions: list[str] = []`. Add a `@model_serializer` that drops `content_value`/`shapes`/`follow_up_questions` when `page_kind` is an obstacle kind (matches `_prune_wire` discipline).
- [x] 5.5 Add `affordances: AffordancesPayload | None = None` to `AskResponse`. Update `_omit_empty` serializer to drop `affordances` when `None`.

## 6. Router and response builder

- [x] 6.1 Add `include_affordances: Annotated[bool, ...]` kwarg to `WebRouter.ask` with description (default `True`; opt out for lean envelope). Pass through to `orchestrate(...)` call.
- [x] 6.2 Update `build_ask_response` to project the package-side `AffordancesPayload` boundary type into the pydantic mirror. Wrap pydantic validation in a try/except — on validation failure (e.g., model returned an out-of-enum value), log a warning and emit `affordances=None`.

## 7. Tests

- [x] 7.1 New file `tests/packages/llm_extract/test_affordances_parse.py`. Test cases: well-formed content page payload parses correctly; well-formed obstacle page payload (no content_value/shapes/follow_ups) parses with defaults; malformed JSON returns None; closed-enum violation surfaces validation error at the pydantic boundary.
- [x] 7.2 New file `tests/capabilities/ask_response/test_affordances_wire.py`. Test cases: default `ask` (no kwarg) includes `affordances` in wire; `include_affordances=False` omits `affordances` from wire; obstacle page omits `content_value`/`shapes`/`follow_up_questions`; content page includes them.
- [x] 7.3 New file `tests/packages/llm_extract/test_prompt_cache_stability.py` extension — assert `EXTRACT_WITH_AFFORDANCES_V1.render(content=X, ask=Y1).cache_prefix == EXTRACT_WITH_AFFORDANCES_V1.render(content=X, ask=Y2).cache_prefix` for varying Y.
- [x] 7.4 Update existing extractor tests to assert `request_affordances=False` is the default and behavior is unchanged.

## 8. Wiring sanity + gates

- [x] 8.1 `make lint` passes (no ASYNC100/210/230 violations, no S101 etc.).
- [x] 8.2 `make ty` passes (closed Literal enums type-check).
- [x] 8.3 `make test` passes with ≥85% coverage.
- [x] 8.4 `make check` passes end-to-end (the gate that runs all three).
- [ ] 8.5 Output-benchmark A/B: run `make bench` with affordances default-on; compare against pre-change baseline; expect parity on the four scoring axes (answer quality, token cost, output clarity, data-contract conformance). Write findings to `eval/findings_<date>-affordances-prod-ab.md`.  (LIVE-NETWORK + LLM QUOTA — deferred to user)

## 9. Documentation + backlog hygiene

- [x] 9.1 Update `CHANGELOG.md` with a v0.20.0 entry: new `affordances` field on `AskResponse`, default-on, opt-out kwarg, new `EXTRACT_WITH_AFFORDANCES_V1` template, marginal +18% cost on `ask`.
- [x] 9.2 Update `CLAUDE.md` if any new conventions emerged (probably none — design follows existing patterns).
- [x] 9.3 Remove the "🟡 Affordances production wiring" item from `BACKLOG.md`; flip the "✅ design fully locked" notes to "✅ shipped".
- [x] 9.4 Bump version in `pyproject.toml` from 0.19 → 0.20.0.
- [ ] 9.5 Refresh global install via `make install-global` so Claude Code's MCP picks up the change on the next session.  (SYSTEM MUTATION — deferred to user)

## 10. Archive

- [ ] 10.1 Run `openspec archive add-affordances-to-ask` after merge.  (post-merge step)
