## 1. Red — prove the bug at the projection level (BDD-first)

- [x] 1.1 Extend the replay contract matcher (`tests/eval_replay/replay.py`): surface `content_md` in `observe(...)` and support `content_excludes` / `content_includes` keys in `assert_contract`.
- [x] 1.2 Add deterministic projection assertions to `regression/hepsiburada-listing-price/baseline/contract.json`: `content_excludes: ["890 TL%21700"]` (the fused token must be gone) and `content_includes: ["~~"]` near the struck price. Confirm the regression replay test now FAILS (red) — it documents the bug at the projection level, offline, no LLM.
- [x] 1.3 Add a focused `record_extract` unit test (`tests/packages/…` or `tests/capabilities/…`) over a minimal `<del>890 TL</del><span>%21</span><span>700 TL</span>` fixture asserting the projected text does not fuse and marks the struck value. Confirm it fails red.

## 2. Fix the projection (`record_extract`)

- [x] 2.1 `detector._own_text`: separate distinct DOM text fragments (single space) so node boundaries survive `_collapse`; general, no value-aware branch. Make 2.1's unit assertion (no fusion) pass.
- [x] 2.2 Preserve strikethrough: when an own-scope descendant is `<del>`/`<s>`/`<strike>`, wrap its text as markdown `~~…~~` in the projected text. Make the struck-price assertion pass.
- [x] 2.3 Verify the existing `record-extraction` tests + four-axis output-benchmark capability tests still pass (no collateral regression from added separators / markup).

## 3. Fitness function (ADR-0003 rule 3)

- [x] 3.1 Add `tests/architecture/test_record_projection_separates_nodes.py`: an AST/behavioral guard that the descendant-flatten in `_own_text` joins with a separator (bans re-introducing the no-separator `"".join` value-blind flatten). Include the acceptance-check docstring (add the bad pattern, confirm red, revert).

## 4. Prove the fidelity fix end-to-end (eval substrate)

- [x] 4.1 Run `make eval-replay CORPUS=regression` — the deterministic projection assertions (1.2) now pass green.
- [x] 4.2 Validated the judged-answer flip with a live LLM against the **frozen bytes** (cleaner than `eval-refresh`, which would byte-drift the captured page): fixed projection + live Haiku answered "700 TL, discounted 21% from 890 TL" (correct) vs the captured "890 TL … 1,700 TL, 48% off" (wrong). Re-recorded `inputs/llm/extract.json` so the cassette stays coherent with the fixed pipeline; `baseline/answer.md` records the before/after.
- [ ] 4.3 (Optional, informational) `make bench` — broader answer-quality / data-contract axes. Deferred; the targeted live validation in 4.2 already proves the flip.

## 5. Wrap

- [x] 5.1 Reconfirm ADR-0004: mark the `record_extract` half **Accepted**; record the two-site reality and re-point the `json-extract` half's confirm-by to its own future change. Update `docs/architecture/extraction-fidelity-program.md` Status (change #2 record_extract half landed).
- [x] 5.2 Update `CHANGELOG.md` (Fixed — record_extract value-blind projection / list-vs-sale fidelity).
- [x] 5.3 `make check` green (lint + ty + test-cov + arch).
- [x] 5.4 `openspec validate typed-extraction-boundary`.
