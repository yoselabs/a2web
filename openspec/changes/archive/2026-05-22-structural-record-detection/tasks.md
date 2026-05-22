## 1. Phase 1 — Tree-aware detector + guards

- [x] 1.1 Split `src/a2web/packages/record_extract.py` into a `record_extract/` folder — `models.py` (`Record`, `RecordSet` boundary dataclasses; `Record` carries per-record `depth`), `detector.py`, `render.py`, `__init__.py` re-exporting the public surface. No `a2web.<domain>` imports.
- [x] 1.2 Implement tree-aware detection in `detector.py` — count each `(tag, first-class-token)` signature document-wide; the chosen signature's occurrences are the records, rooted at their lowest common ancestor; content-bearing test uses own-scope text/links (excluding nested same-signature child-records).
- [x] 1.3 Implement the four guards — non-empty class token; parent-signature consistency ≥ 0.70; heading-presence ≥ 0.50 (`h1`–`h6` / `[role=heading]`); ancestor tie-break on a near-tie. Reject a signature unless guards (a)–(c) all hold.
- [x] 1.4 Implement depth-aware rendering in `render.py` — flat record set → flat list; threaded record set → indentation by nesting depth; each record rendered in own scope, no child-record text duplicated into its parent.
- [x] 1.5 Capability tests for `record_extract`: flat listing → records at depth 0; threaded discussion → records with depth > 0, no double-counting; reference-doc `<section>` (empty class) → no region; scattered chrome (low consistency) → no region; article prose `<p>` (no headings) → no region.
- [x] 1.6 Confirm `tests/test_packages_independence.py` passes — the `record_extract/` folder has zero `a2web.<domain>` imports.
- [x] 1.7 `make check` green for Phase 1 — lint, `ty`, full suite, coverage ≥ 85%.

## 2. Phase 2 — Remove the recall trigger

- [x] 2.1 Delete `trafilatura_under_extracted`, `_visible_text_length`, `_UNDER_EXTRACTED_RATIO`, `_NEAR_EMPTY_FLOOR`, and the already-dead `count_sentences` / `_SENTENCE_END_RE` from `domain.py`; drop them from `__all__` and from `fetcher.py`'s imports.
- [x] 2.2 `_run_extraction_escalation` runs the ladder unconditionally — no trigger gate; each rung self-gates (`json_in_script` on JSON presence, record extraction on the detector guards). Update its docstring.
- [x] 2.3 Tests: the ladder runs for any page; a genuine article reaches the record rung, the rung returns no region, `content_md` is unchanged; the near-empty → browser path still fires via the gate's length floor.
- [x] 2.4 `make check` green for Phase 2 — lint, `ty`, full suite, coverage ≥ 85%.

## 3. Phase 3 — Depth-aware replace + dual-link next_links

- [x] 3.1 Make `_escalate_via_records`'s replace decision depth-aware — a threaded (depth > 0) record set replaces `content_md` whenever produced; a flat (depth 0) record set replaces only when its render is longer than trafilatura's output.
- [x] 3.2 Rework `_records_to_next_links` for dual-link emission — per flat-record-set record emit up to two `NextLink`s: `kind="source"` (heading link) and `kind="discussion"` (same-host permalink identified by a comment-count anchor / thread-path); dedup by URL; skip archive-mirror hosts. A threaded record set emits no `next_links`.
- [x] 3.3 Confirm the `NextLink` `kind` surface carries `source` / `discussion` values; adjust the closed set if needed.
- [x] 3.4 Tests: a threaded record set replaces a flattened wall regardless of length; a flat catalog replaces on length; an aggregator record emits both `source` and `discussion`; a record with only a heading link emits one; a threaded record set emits no `next_links`.
- [x] 3.5 `make check` green for Phase 3 — lint, `ty`, full suite, coverage ≥ 85%.

## 4. Verify

- [x] 4.1 Run `make bench` (live-network, spends LLM quota — user-gated); confirm lobste.rs (home + comment thread) and Douban listing extraction improve and no article regresses; record findings in `eval/findings_<date>.md`.
