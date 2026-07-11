## 1. Meta allowlist on AskResponse

- [x] 1.1 Locate the `AskResponse(...)` construction site (`build_ask_response` / `fetcher_response.py:376,523` area) and add a `_curate_ask_meta(meta_dict) -> dict[str, str]` helper that projects only the allowlisted keys (`og.description`, `og.site_name`, plus non-redundant `jsonld[0].*` keys — explicitly EXCLUDE `og.title`, it duplicates the already-promoted top-level `title` field; verify the final list against 2-3 live fixtures per design D2).
- [x] 1.2 Wire the helper into the `ask`-path construction only; confirm `fetch_raw`'s `FetchResponse.meta` is untouched (still the full raw dict).
- [x] 1.3 Add/update tests for the new `ask-response` spec requirement "AskResponse meta is curated to an allowlist" (allowlist keys present, non-allowlist keys absent, empty-after-curation omits `meta` entirely, `fetch_raw` unaffected).
- [x] 1.4 (Addendum, design D6) Drop `og.site_name` from `_ASK_META_ALLOWLIST` in `fetcher_response.py`, leaving `("og.description",)`. Updated `test_ask_meta_curates_to_allowlist` (and its `_RICH_META_HTML` fixture assertions) to expect `og.site_name` absent. `tests/contracts/ask_success_rich.json` did not need re-blessing — `blog.html` carries no allowlisted key regardless, so its `meta` shape was already empty/omitted before and after this change.

## 2. Remove genre from the router-shape envelope

- [x] 2.1 Remove the `genre` field from `AskResponse` (`models.py`) and from `RouterPayload` (wherever it's declared — likely `packages/llm_extract/` boundary types per CLAUDE.md's `RouterPayload boundary type lives in packages/llm_extract` note).
- [x] 2.2 Remove the `genre` field/examples from `EXTRACT_ROUTER_V1`'s `tail_template` JSON schema description in `prompts.py` (the field description block and both worked examples that include `"genre": "..."`).
- [x] 2.3 Update `_ASK_REQUIRED_FIELDS` / `_prune_wire` call sites and any comment referencing "seven router-shape fields" to "six."
- [x] 2.4 Update existing tests referencing `genre` (search `tests/` for `genre`) — remove or adapt per the MODIFIED requirements in `specs/ask-response/spec.md`.
- [x] 2.5 Confirm a stray `genre` key from a non-conforming/stale-cached extractor response is tolerated (pydantic ignores unknown keys by default) rather than raising — add the "stray genre key is ignored" scenario as a test.

## 3. Prompt tuning: token-efficiency + partial-signal honesty

- [x] 3.1 Decide the versioning approach (design open question): bump `EXTRACT_ROUTER_V1.version` to `2` in place, or introduce `EXTRACT_ROUTER_V2` — check how the eval harness's reflection-based template discovery keys templates (by `name`, `version`, or the module constant) before deciding. **Resolved:** bumped `version=2` in place (same `name`); router-shape calls bypass the extraction cache entirely (`request_routing=True` skips cache lookup), so there's no cache-key staleness risk either way.
- [x] 3.2 Add the token-efficiency instruction to `system` (terse framing, zero fact/identifier/number loss, ASCII-preferring punctuation in the model's own prose, verbatim-quote rule unaffected).
- [x] 3.3 Add the partial-signal honesty instruction to `system` (report what IS present when full detail is missing, rather than denying the topic; genuinely absent topics are still reported absent).
- [x] 3.4 Verify `cache_prefix_template` remains byte-identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template` (the v0.19 cache-prefix invariant) — the existing `test_router_template_cache_prefix_matches_base_template` test already covers this and passes.
- [x] 3.5 Add unit-level coverage for the two new `extraction` spec requirements (terseness instruction present + cache prefix untouched; partial-signal instruction present in `system`). Live-model behavioral verification (e.g. "does the model actually preserve a cited number") is a `make bench` concern (task 4.2), not unit-testable.

## 4. Verification

- [x] 4.1 Run `make check` (lint + ty + test, coverage ≥85%). All green: lint clean, ty clean, arch invariants clean, 992 tests passed, 89.81% coverage. Golden contracts re-blessed (`ask_success_rich.json` drops `meta` — blog.html has no allowlisted keys; `tool_schemas.json` drops `genre` from both `AskResponse` and `RouterPayload` schemas) and diff-reviewed before committing — matches the intended change exactly.
- [ ] 4.2 Run `make bench` (live-network, spends quota — manual, deliberate step per CLAUDE.md) comparing pre/post-tuning on the four axes (answer quality, token cost, output clarity, contract conformance). **Deliberately skipped this session** — quota-constrained; see `eval/findings_2026-07-09-ask-extraction-token-tuning.md`. Run when quota allows, before treating the prompt-tuning payoff as confirmed.
- [x] 4.3 Write findings to `eval/findings_<date>.md` per existing convention — done as `eval/findings_2026-07-09-ask-extraction-token-tuning.md`, documenting what was verified for free vs. deferred.
- [~] 4.4 Re-run the original two live repro calls. **Partially done without spending LLM quota**: probed both URLs via `fetch_raw` (no LLM) and ran the real live `meta` dict through `_curate_ask_meta` in-process — confirmed 18→2 keys on androidheadlines.com, `og.title` correctly excluded; androidexperto.com had empty raw meta already. `genre` absence confirmed structurally via `make check`'s contract snapshot. **Not confirmed**: the actual partial-signal answer-text change on a live `ask` call — that needs LLM quota, deferred alongside 4.2.
