## 0. Prerequisite (blocks everything with a cost)

- [ ] 0.1 `bench-cost-isolation` change is applied — cheap/subscription bench + per-item + per-axis isolation exist. The spikes below MUST NOT run on the metered Anthropic API.
- [ ] 0.2 The parallel in-flight feature has landed (this change is a breaking rename; do not interleave).

## 1. Spikes — validate before renaming anything (subscription/cheap provider only)

- [ ] 1.1 Spike A: phrasing matrix {full-sentence, query-grammar, bare-keyword} over ~8–10 items spanning fork/compound/qualifier/list. Measure Judge quality + token cost. Confirm query-grammar is lossless vs sentence and bare-keyword drops fork/qualifier. Write `eval/spikes/query-grammar-A.md`.
- [ ] 1.2 Spike B: CAPS A/B on fork + qualifier subset; measure constraint-respect. Decide whether to prescribe CAPS. Write findings.
- [ ] 1.3 Spike C: generate queries from LEAN vs FAT description, run through Spike A; pick the shortest description that holds fidelity. Write findings.
- [ ] 1.4 Lock the final grammar + description text from spike results.

## 2. Extraction prompt

- [ ] 2.1 In `src/a2web/packages/llm_extract/prompts.py`, change the `EXTRACT_ROUTER_V1` follow-up instruction from full questions to query grammar (target + operator; CAPS the decider per Spike B; split `and` compounds; `?` only for DECIDE).
- [ ] 2.2 Bump the template version per convention; update the version-history comment.

## 3. Rename cascade (breaking)

- [ ] 3.1 `src/a2web/routers.py`: rename tool `ask` → `query`, param `question` → `query`, move `canonical_name_override` to `query`, install the locked tool description.
- [ ] 3.2 `src/a2web/models.py`: rename `AskResponse.ask_here` → `refine`; update `_prune_wire` / serializer wiring.
- [ ] 3.3 `src/a2web/fetcher_response.py`: update `_project_routing` field mapping `ask_here` → `refine`.
- [ ] 3.4 Grep for all `ask_here` / `"ask"` tool-name / `question=` references across `src/` and `tests/`; update.

## 4. Tests & contracts

- [ ] 4.1 Update `tests/contracts/*.json` and tool-schema fixtures for the new tool name + param + `refine` field.
- [ ] 4.2 Update capability tests under `tests/capabilities/ask_response/`.
- [ ] 4.3 `make check` green (lint + ty + test, coverage ≥85%).

## 5. Ship

- [ ] 5.1 Version bump + CHANGELOG entry noting the breaking rename.
- [ ] 5.2 `make install-global`; update `~/.claude.json` MCP entry if the tool name is referenced there.
- [ ] 5.3 One live `query` call to sanity-check the new surface end-to-end.
