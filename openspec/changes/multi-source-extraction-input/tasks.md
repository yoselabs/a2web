## 1. Red — prove the bug at the menu level (BDD-first)

- [ ] 1.1 Extend the replay observer (`tests/eval_replay/replay.py`): surface the debug `content_candidates[]` in `observe(...)` (it replays with `debug=True`) and add an `input_menu_includes` / `input_menu_excludes` contract key in `assert_contract` that asserts against the concatenation of candidate `content_md` (what Haiku was fed), independent of the wire `content_md`.
- [ ] 1.2 Add deterministic menu assertions to `regression/recipe-nutrition-volume-gate/baseline/contract.json`: `input_menu_includes: ["268", "kcal"]` (the answer-bearing source must reach the extractor). Confirm the regression replay now FAILS red — today only the sidebar `record_synth` reaches Haiku, so `268`/`kcal` are absent from the input menu.
- [ ] 1.3 Add a focused unit test (`tests/capabilities/extraction/…`) over a minimal page with a long junk record region + a short JSON-LD carrying the answer: assert the assembled extractor menu contains the JSON-LD answer and is NOT just the longest source. Confirm it fails red.

## 2. Collect the menu (retire single-winner selection)

- [ ] 2.1 `_run_extraction_escalation`: stop picking a winner. Always append a `trafilatura` `ContentCandidate` for the prose baseline, then every non-empty `json_synth` / `record_synth` candidate, into an immutable `fc.content_candidates: list[ContentCandidate]` (fixed order prose → json_synth → record_synth). Remove the `len(synthetic) > original_len` replace checks from `_escalate_via_json` / `_escalate_via_records` (keep their LDD events + pure shape). Document the retired volume-gate rationale in a code comment + CHANGELOG.
- [ ] 2.2 Wire default (`fc.content_md`): set by the quality rule — prose candidate when non-empty, else first structured candidate, else `fc.pre_rendered_payload`. Length is never the selector. Keep `fc.next_links_handler` sourced from the records candidate as today.
- [ ] 2.3 `ContentCandidate.source` Literal already covers `trafilatura`/`json_synth`/`record_synth`; confirm the prose candidate uses `source="trafilatura"`.

## 3. Assemble + feed the menu to the extractor

- [ ] 3.1 Add a pure domain helper (in `fetcher.py` / `domain.py`) `assemble_menu(candidates) -> str`: coarse subset-suppression (drop a candidate whose normalized text is a strict substring of another), then deterministic concatenation with static content-free section labels. No timestamps / counts / identity / dict-order. Make 1.3's unit assertion pass.
- [ ] 3.2 Priority-aware trim: when the menu would exceed `max_content_chars`, trim `record_synth` first, prose + `json_synth` last (static priority table). Reuse the extractor's `_truncate` as the total backstop.
- [ ] 3.3 `_phase_extract_answer`: pass `extract(content=assemble_menu(fc.content_candidates))` instead of `content=fc.content_md`. No change to `extractor.extract`'s signature (package boundary unchanged).

## 4. Wire envelope — debug-only content_candidates (Ask-First: signed off 2026-06-07)

- [ ] 4.1 Add `content_candidates: list[ContentCandidate]` as a flat attribute on `FetchResponse` (`models.py`); populate it in `build_response` from `fc.content_candidates` as `{source, content_md}` entries.
- [ ] 4.2 `_prune_wire`: regroup `content_candidates` into the wire-only `debug` object (present only under `debug=True`, exactly like `tokens` / `cache` / `extraction`). Default wire shape must stay byte-identical — confirm with the existing fetch-response envelope tests.

## 5. Cost + fitness functions

- [ ] 5.1 Verify the `EXTRACT_*` cache-prefix byte-equality test still passes (menu as content must not break the `cache_prefix = {content}` invariant for repeated asks on one page). Add a test: `assemble_menu` is byte-identical for two different asks on the same candidate list.
- [ ] 5.2 Add `tests/architecture/test_menu_assembly_is_pure.py`: a behavioral guard that `assemble_menu` is a pure function of its input (same candidates → same bytes; bans reintroducing length-as-selector in the escalators). Include the acceptance-check docstring (add a non-deterministic element, confirm red, revert).

## 6. Prove the fidelity fix end-to-end (eval substrate)

- [ ] 6.1 Run `make eval-replay CORPUS=regression` — the menu assertions (1.2) now pass green; the deterministic axis proves the answer-bearing source reaches Haiku.
- [ ] 6.2 Validate the judged-answer flip with a live LLM against the **frozen bytes** (as in change #2): fixed menu + live Haiku answers "268 kcal, 34g sugar" (correct) vs the captured "no nutrition, it's a listing" (wrong). Re-record `inputs/llm/extract.json`; update `baseline/answer.md` before/after.
- [ ] 6.3 Re-run the four-axis output-benchmark capability tests (`tests/capabilities/output_benchmark/`) — confirm no collateral regression on legitimately record-shaped pages (listings, threaded discussions) from the prose-preferred wire default.

## 7. Wrap

- [ ] 7.1 Reconfirm ADR-0005: move `Status` from *Accepted (provisional)* to *Accepted*; record the measured cost delta and the record-detector-false-positive finding (handed to ADR-0007). Update `docs/architecture/extraction-fidelity-program.md` Status (change #3 landed).
- [ ] 7.2 Update `CHANGELOG.md` (Fixed — extraction fed the full multi-source menu; volume gate retired; Added — debug `content_candidates`).
- [ ] 7.3 `make check` green (lint + ty + test-cov + arch).
- [ ] 7.4 `openspec validate multi-source-extraction-input`.
