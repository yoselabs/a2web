## 1. Prompt template — EXTRACT_ROUTER_V1

- [x] 1.1 Add `EXTRACT_ROUTER_V1` to `src/a2web/packages/llm_extract/prompts.py`. System paragraph + tail covering: `structural_form` (9-value closed enum, one-liner each), `shape` (7-value, including new `discussion`), `genre` (7-value, optional, omit-when-none rule), `obstacle` (4-value, optional, omit-on-healthy rule), `ask_here` rule (obvious-filler cut, "context decides count, 3 good 5 great"), `try_url` rule (Q-conditioned reasons ≤120c, "context decides count"), one JSON envelope example showing omit-empty pattern. **Discussion-shape generosity hint**: when `shape=discussion`, the tail SHALL instruct the model to lean toward more `ask_here` items (5+ acceptable) because thread pages support more useful follow-ups about positions, dissent, consensus, top voices.
- [x] 1.2 Confirm `cache_prefix_template` is byte-identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template`. Differ only in `tail_template`.
- [x] 1.3 Target tail length ≤550 tokens (~−35% vs v0.20 affordances tail). Verify with token counter.
- [x] 1.4 Export `EXTRACT_ROUTER_V1` from `packages/llm_extract/__init__.py`. Drop `EXTRACT_WITH_AFFORDANCES_V1` export.

## 2. Boundary type — RouterPayload

- [x] 2.1 Create `src/a2web/packages/llm_extract/router_payload.py` with `RouterPayload` frozen `@dataclass(slots=True)`: fields `answer: str`, `structural_form: str`, `shape: str`, `genre: str | None = None`, `obstacle: str | None = None`, `ask_here: tuple[str, ...] = ()`, `try_url: tuple[NextUrlBoundary, ...] = ()`.
- [x] 2.2 In the same module, add `NextUrlBoundary` frozen dataclass with `url: str` and `reason: str`.
- [x] 2.3 Export both from `packages/llm_extract/__init__.py`. Drop `AffordancesPayload` / `AffordanceShape` exports.
- [x] 2.4 Delete `src/a2web/packages/llm_extract/affordances.py` (no backward-compat alias).
- [x] 2.5 Verify `tests/test_packages_independence.py` still passes (no `a2web.<domain>` imports in the new module).

## 3. Extractor wiring

- [x] 3.1 Rename `request_affordances` → `request_routing` throughout `src/a2web/packages/llm_extract/extractor.py`.
- [x] 3.2 Swap template selection: `active_template = EXTRACT_ROUTER_V1 if request_routing else self._template`.
- [x] 3.3 Rename `_split_answer_and_affordances` → `_split_answer_and_routing`. Update parser to extract the 7 router-shape fields (3 required + 4 optional). On missing required fields (answer / structural_form / shape), return `(answer_text, None)` so `routing` is set to `None`.
- [x] 3.4 Update `_OBSTACLE_KINDS` reference: drop the obstacle-omit logic on inline fields (router-shape doesn't have inline fields to omit); replace with simple "if obstacle is set and structural_form/shape missing, return None" check.
- [x] 3.5 Rename `ExtractionResult.affordances: AffordancesPayload | None` → `routing: RouterPayload | None`. Cache lookups/writes skip when `request_routing=True` (matches current `request_affordances` skip behavior).
- [x] 3.6 Update extractor structlog event names: `affordances_*` → `routing_*`.

## 4. LlmExtractorResource and fetcher plumbing

- [x] 4.1 Rename `request_affordances` → `request_routing` kwarg in `src/a2web/llm_resource.py`. Pass through to `Extractor.extract`.
- [x] 4.2 Rename `include_affordances` → `include_routing` kwarg in `src/a2web/fetcher.py::fetch`. Thread through `FetchContext.include_routing`.
- [x] 4.3 Rename `FetchContext.affordances: AffordancesPayload | None` → `routing: RouterPayload | None`.
- [x] 4.4 In `_phase_extract`, pass `request_routing=fc.include_routing` into the extractor call; set `fc.routing = result.routing`.

## 5. Domain pydantic mirrors

- [x] 5.1 In `src/a2web/models.py`, drop `AffordancesPayload`, `AffordanceShape`, `PageKind`, `PageKindConfidence`, `ContentValue`, `ShapeLabel`, `_OBSTACLE_PAGE_KINDS`.
- [x] 5.2 Add new literal types: `StructuralForm = Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]`, `Shape = Literal["prose","records","key-value","code","table","discussion","mixed"]`, `Genre = Literal["news","encyclopedia","spec","paper","personal","official","community"]`, `Obstacle = Literal["paywalled","blocked","empty","error"]`.
- [x] 5.3 Add pydantic `NextUrl` model: `{url: str, reason: str}`.
- [x] 5.4 Add pydantic `RouterPayload` model with the 7 router-shape fields (3 required + 4 optional with proper defaults).
- [x] 5.5 Drop the `affordances: AffordancesPayload | None` field from `AskResponse`. **Rename** the existing `extracted_answer: str` field to `answer: str` (specs say `answer`; cleaner since we're already breaking). Add 6 new fields: `structural_form`, `shape`, `genre`, `obstacle`, `ask_here`, `try_url`. Net surface change: −1 field (`affordances`) + −1 rename (`extracted_answer` → `answer`) + +6 new = 7 router-shape fields total.
- [x] 5.6 **Rewrite** `AskResponse._envelope_discipline` model_serializer: drop the obstacle-cluster omit logic (no longer applies — no inline fields depend on obstacle). Add omit-empty for the 4 new conditionals: `genre` when `None`, `obstacle` when `None`, `ask_here` when `[]`, `try_url` when `[]`. The shared `_prune_wire` helper's signature stays the same; only the per-call params for `AskResponse` change.

## 6. Response builder

- [x] 6.1 Rename `_project_affordances` → `_project_routing` in `src/a2web/fetcher_response.py`. Use `RouterPayload.model_validate({...})` (per v0.20 pattern that side-steps ty's strict Literal checking).
- [x] 6.2 Try/except around validation: on failure, log a warning and leave all 7 router-shape fields absent (the unstructured `answer` text on `AskResponse` is unaffected).
- [x] 6.3 Update `build_response` and `build_ask_response` to pass `routing` through and project the 7 fields onto `AskResponse`.

## 7. Router (tool surface)

- [x] 7.1 Rename `include_affordances` → `include_routing` kwarg in `src/a2web/routers.py::WebRouter.ask`. Update the `Annotated[bool, Field(description="...")]` description to reflect the router-shape semantics (default `True`; opt out for lean envelope).

## 8. Claude Code provider isolation

- [x] 8.1 In `src/a2web/packages/llm_extract/providers/claude_code.py`, add `mcp_servers={}`, `strict_mcp_config=True`, `agents={}` to `options_kwargs` (alongside existing `setting_sources=[]`, `skills=[]`, `extra_args={"disable-slash-commands": None}`).
- [x] 8.2 Surface `num_turns` from `ResultMessage` into `ProviderResponse.raw["num_turns"]`. Verify the existing `max_turns=1` cap holds by asserting `num_turns == 1` in a smoke test.
- [x] 8.3 Update the `# Bare-mode opt-outs` comment block to document the new isolation fields and the leak path they close ("MCP server config from host Claude Code CLI, including memory-bearing servers like hub_memory_recall").

## 9. Tests

- [x] 9.1 Move `tests/packages/llm_extract/test_affordances_parse.py` → `test_router_parse.py`. Update tests to assert RouterPayload construction with: full healthy payload, payload with obstacle, payload with only `ask_here` populated, payload with malformed JSON, payload missing required fields, payload with unknown enum values.
- [x] 9.2 Move `tests/capabilities/ask_response/test_affordances_wire.py` → `test_router_wire.py`. Update tests to assert: default `ask` (no kwarg) includes the 3 required fields, omits empty optionals; `include_routing=False` omits all 7; obstacle page populates `obstacle` and `try_url`; healthy page omits all 4 conditionals; parse failure leaves all 7 absent but `answer` intact.
- [x] 9.3 Update `tests/packages/llm_extract/test_prompt_cache_stability.py` to test `EXTRACT_ROUTER_V1` (assert byte-identity to `EXTRACT_CACHEABLE_V1.cache_prefix`, byte-stability across asks, schema enums in tail not prefix). Drop the v0.20 `EXTRACT_WITH_AFFORDANCES_V1` assertions.
- [x] 9.4 Update any tests asserting on `AskResponse.affordances` to assert on the new 7 fields.
- [x] 9.5 Re-bless `tests/contracts/{ask_debug.json, tool_schemas.json}` via `make bless-contracts` to absorb the template name change + kwarg rename + new field schema.
- [x] 9.6 Add a smoke test asserting the claude_code provider's `ClaudeAgentOptions` carries `mcp_servers={}`, `strict_mcp_config=True`, `agents={}` (mock the SDK; verify the options dict shape).

## 10. Wiring sanity + gates

- [x] 10.1 `make lint` passes (no ASYNC100/210/230 violations).
- [x] 10.2 `make ty` passes (Literal closed enums type-check).
- [x] 10.3 `make test` passes with ≥85% coverage.
- [x] 10.4 `make check` passes end-to-end.
- [ ] 10.5 Re-run the post-impl eval (`eval/spikes/surface_eval_v3_prod.py` — extended from v1/v2 with corpus additions for `discussion`-shape pages: hn-thread, reddit-rust-thread, lobste-thread, blog-with-comments). Capture findings as `eval/findings_2026-05-25-router-shape-prod-eval.md`. Targets: cost saving ≥−10% vs v0.20 baseline, zero parse failures, `shape=discussion` correctly picked on all 4 thread URLs, soft `try_url` rule recovers MDN / wiki / HN-front drilldowns lost in spike v1, `genre` populated sensibly (not over-emitted, not always omitted), no memory leaks in answer or ask_here text.
- [ ] 10.6 Manual smoke: invoke `a2web web ask --url=<test> --question=<test>` and verify memory leak gone (no "Denis's…" / "your…" / personal-context phrases in answer or ask_here).
- [ ] 10.7 Output-benchmark A/B (`make bench`): run with router shape, compare against v0.20 baseline. (LIVE-NETWORK + LLM QUOTA — deferred to user.)

## 11. Documentation + backlog hygiene

- [x] 11.1 Update `CHANGELOG.md` with a v0.21.0 entry: framed as a clean supersession of v0.20.0 affordances surface (one-release lifespan; design refined through three exploration spikes after shipping). List BREAKING changes (7-field surface replaces single `affordances` field; kwarg renames).
- [x] 11.2 Update `CLAUDE.md` — replace the affordances architecture paragraph in the WebRouter section with the router-shape description (7 fields, 3 required, 4 conditional via `_prune_wire`, axis-decomposed typing, new `discussion` shape, soft caps).
- [x] 11.3 Update `BACKLOG.md`: close the affordances item (already "shipped" from v0.20 — now supersede with "✅ shipped → superseded by router-shape v0.21"); open `extract` tool with consumer-supplied schema item; open `page_kind_confidence` resurrection item (only if a real consumer asks).
- [x] 11.4 Bump version in `pyproject.toml` from 0.20.0 → 0.21.0.
- [ ] 11.5 Refresh global install via `make install-global` so Claude Code's MCP picks up the change. (SYSTEM MUTATION — deferred to user.)

## 12. Archive

- [ ] 12.1 Run `openspec archive refactor-ask-to-router-shape` after merge to apply the deltas to canonical specs and move the change into `openspec/changes/archive/`.
