## 1. Phase 1 — Recall-based escalation trigger

- [x] 1.1 Add a pure recall-signal helper — measure trafilatura `content_md` against the substantive content present in the raw HTML (visible-text volume / discarded-region size); return a "trafilatura under-extracted" boolean.
- [x] 1.2 Replace the `_JSON_SYNTH_THIN_CHARS` / sentence-count length gate in `_maybe_synthesize_from_json` with the recall trigger; keep a near-empty absolute floor that forces escalation regardless of recall.
- [x] 1.3 Tests: a complete short-article fixture does NOT escalate; a gutted-listing fixture (short `content_md`, large discarded region) DOES escalate; near-empty `content_md` escalates regardless of recall.
- [x] 1.4 `make check` green for Phase 1 — lint, `ty`, full suite, coverage ≥ 85%.

## 2. Phase 2 — Structural record extractor + escalation ladder

- [x] 2.1 New `src/a2web/packages/record_extract/` — package-owned `Record` / `RecordSet` boundary dataclasses; implement C1: locate the dominant repeated record region (container with the most content-bearing repeats of one structural signature; rank by record count × per-record text so chrome ranks below).
- [x] 2.2 Implement C2: render a located region to link-preserving markdown over the bounded subtree only — retain every link per record, never pick a single "primary" link.
- [x] 2.3 Capability tests for `record_extract`: GitHub-trending fixture → repo-card region beats marketing nav; flat-list fixture → list located; article fixture → no region; near-empty shell → no region (no speculative output).
- [x] 2.4 Generalize `_maybe_synthesize_from_json` into the multi-source ladder — `json_in_script` source then `record-extraction` source — stopping at the first passing result, clean fall-through when none pass; emit `StageStarted` / `StageEnded` LDD events naming each source.
- [x] 2.5 Implement the quality-aware replace check — a dominant substantive record cluster (minimum count, each record with text + a link) replaces `content_md`; length alone never wins. Removes the `≥2× chars` rule.
- [x] 2.6 Domain seam — convert `record_extract` per-record candidates to `NextLink` (each record's prominent heading link); thread into `FetchResponse.next_links`.
- [x] 2.7 Tests: the ladder routes a server-rendered listing (no embedded JSON) to record extraction; a good article is never clobbered by a competing record cluster; `next_links` is populated for an un-handled listing URL.
- [x] 2.8 Confirm `tests/test_packages_independence.py` passes — `record_extract` has zero `a2web.<domain>` imports.
- [x] 2.9 `make check` green for Phase 2 — lint, `ty`, full suite, coverage ≥ 85%.

## 3. Phase 3 — JSON-LD ItemList synthesis + GitHub reserved-path fix

- [x] 3.1 Extend `json_to_markdown_rows` (`domain.py`) to render a JSON-LD `ItemList` — an `itemListElement` array of `ListItem` entries — into record rows carrying item name and url.
- [x] 3.2 Tests: a populated `ItemList` payload renders one row per item; an empty / malformed `ItemList` yields no rows and the ladder continues.
- [x] 3.3 Add reserved top-level paths (`trending`, `sponsors`, `collections`, `explore`, `topics`, `about`, …) to `GitHubHandler._classify`'s skip-set; test that `github.com/trending/python` no longer false-matches the repo shape.
- [x] 3.4 `make check` green for Phase 3 — lint, `ty`, full suite, coverage ≥ 85%.

## 4. Verify

- [ ] 4.1 Run `make bench` (live-network, spends LLM quota — user-gated); confirm `gh-trending` moves 0 → passing and `next_links` is populated on listing URLs; record findings in `eval/findings_<date>.md`.
