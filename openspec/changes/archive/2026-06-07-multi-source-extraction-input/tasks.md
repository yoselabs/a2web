> **Scope pivot (2026-06-07, decision B).** The instrument caught a blind fix:
> `regression/recipe-nutrition-volume-gate` is NOT menu-fixable alone —
> `json_to_markdown_rows` can't render `Recipe`/`NutritionInformation` (returns
> `""`), so `268` never reaches the menu even with the fix. That case is routed
> to **change #4 (ADR-0004 json half)**; its `input_menu_includes` RED assertion
> moves there. Change #3 = the menu + JSON-emits-all-payloads (pure ADR-0005),
> proven by the deterministic menu unit + arch fitness tests (1.3 / 5.2). A live
> menu-flipping regression is the remaining corpus proof (task 6.2).

## 1. Red — prove the menu fix deterministically (BDD-first)

- [x] 1.1 Extend the replay observer (`tests/eval_replay/replay.py`): cassette spy (`CassetteLlm.last_extract_content`) records what Haiku was fed; `observe(...)` surfaces it as `input_menu`; `assert_contract` gains `input_menu_includes` / `input_menu_excludes` (assert the menu, not the wire — ADR-0005 D7). Intent keys preserved on re-bless.
- [x] 1.2 ~~recipe menu assertion~~ → **routed to change #4** (recipe needs json rendering; not menu-fixable). Recipe contract restored to the documented-bug baseline; `answer.md` records the compound finding.
- [x] 1.3 Focused unit tests (`tests/capabilities/extraction/test_menu_assembly.py`): a short JSON answer reaches the menu despite far-longer records; the JSON rung emits ALL renderable payloads (answer in a non-top-ranked one survives); `assemble_menu` is pure + dedups. (Red confirmed by the arch acceptance check in 5.2.)

## 2. Collect the menu (retire single-winner selection)

- [x] 2.1 `_run_extraction_escalation`: stop picking a winner. Append a `trafilatura` `ContentCandidate`, then ALL `json_synth` / `record_synth` candidates, into immutable `fc.content_candidates` (fixed order prose → json → records). Length gate removed from `_escalate_via_json` / `_escalate_via_records` (LDD events kept; outcome now `collected`).
- [x] 2.2 Wire default (`fc.content_md`): `_pick_display_candidate` PRESERVES the legacy selection (json-if-longer, record-if-threaded-or-longer, else prose) — wire byte-identical per the signed-off "wire unchanged" decision. The retired length proxy now lives ONLY here as a display heuristic, no longer gating the extractor input. `next_links` sourced from the records candidate.
- [x] 2.3 `ContentCandidate` gains `is_threaded` (the one non-length display signal); prose candidate uses `source="trafilatura"`.

## 3. Assemble + feed the menu to the extractor

- [x] 3.1 `assemble_menu(candidates) -> str` (in `fetcher.py`): coarse subset-suppression (`_suppress_subsets` — strict-substring + exact-dup), deterministic concatenation with static labels. Pure (no timestamps/counts/identity/dict-order).
- [x] 3.2 Priority trim by ORDERING: menu order prose → json → records means the extractor's existing tail-truncation cap drops the lowest-priority source (records) first — no second cap pass, keeping the menu byte-stable (D2). `_truncate` is the backstop.
- [x] 3.3 `_phase_extract_answer`: `extract(content=assemble_menu(fc.content_candidates) or fc.content_md)` (fallback covers handler/pre-rendered pages with no candidates). No `extractor.extract` signature change — package boundary unchanged.
- [x] 3.4 JSON rung emits ALL renderable payloads (not just top-ranked + break) — the single-source class one level down.

## 4. Wire envelope — debug-only content_candidates (Ask-First: signed off 2026-06-07)

- [x] 4.1 `ContentCandidateWire(source, content_md)` model; flat `content_candidates` attribute on `FetchResponse`; populated in `build_response` (only under `debug`).
- [x] 4.2 `_prune_wire`: `content_candidates` added to `_FETCH_DEBUG_FIELDS` → regrouped under `debug`, absent on the default wire. Envelope tests green; tool-schema golden re-blessed (purely additive).

## 5. Cost + fitness functions

- [x] 5.1 `EXTRACT_*` cache-prefix byte-equality test still green; `assemble_menu` byte-stability asserted (`test_assemble_menu_is_byte_stable`) — the `cache_prefix = {content}` invariant holds (same page → same menu → same prefix across asks).
- [x] 5.2 `tests/architecture/test_menu_assembly_is_pure.py`: behavioral guards (a short structured candidate is collected despite far-longer prose — bans re-introducing the length gate; `assemble_menu` byte-stable). Acceptance-check docstring included.

## 6. Prove the fidelity fix end-to-end (eval substrate)

- [x] 6.1 `make eval-replay CORPUS=regression` green (Hepsiburada fixed; recipe documents the bug pending change #4; byte-exact LLM reproduction holds).
- [ ] 6.2 Capture a live MENU-ONLY regression (decision B): a page where a renderable rung holds a short answer the volume gate dropped (e.g. product price in JSON-LD, longer prose). Freeze it; assert `input_menu_includes:[answer]` (GREEN with the menu, RED without — the acceptance check). The recipe case's judged-flip belongs to change #4.
- [x] 6.3 Four-axis output-benchmark capability tests pass — no collateral regression (the legacy display pick keeps record-shaped pages' `content_md` unchanged).

## 7. Wrap

- [ ] 7.1 Reconfirm ADR-0005: move `Status` to *Accepted*; record the JSON-rung single-source finding + the recipe→change-#4 routing. Update `docs/architecture/extraction-fidelity-program.md` Status.
- [ ] 7.2 Update `CHANGELOG.md` (Fixed — extractor fed the full multi-source menu; volume gate retired from the input path. Added — debug `content_candidates`).
- [x] 7.3 `make check` green (lint + ty + test-cov + arch). 836 passed.
- [ ] 7.4 `openspec validate multi-source-extraction-input`.
