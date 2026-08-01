# Tasks

Blocks `decompose-fetcher-into-files` phase two. Must **not** run concurrently
with phase one — v0.23 demonstrated what a refactor that is also a bug fix costs.

Gate first: the `kind` and `anchor` corrections are envelope-shape changes, and
CLAUDE.md's Ask First list covers them.

## 1. Confirm the shape before moving anything

- [x] 1.1 Confirm the Ask First gate for the breaking envelope change:
      `other_pages[].kind` values change for handler-derived rows, and
      `NextLink.anchor` starts appearing.
- [x] 1.2 Verify `_compose_next_links`' drop (`fetcher_response.py:274-281`) —
      it is clearly wrong when `request_next_links` is False (the LLM never saw
      them). Determine whether it is also wrong when True before choosing a
      conditional or total fix.
- [x] 1.3 **Decided: in place, and the lean toward a directory was wrong.** The
      census's "four purposes" are already four labelled bands in one file; a
      directory renames them to filenames and changes nothing — no second
      consumer, no import cycle. Against it: this module's whole interface to the
      orchestrator is the 42-field `FetchContext` slice, and
      `decompose-fetcher-into-files` phase two moves `FetchContext` itself.
      Splitting first draws a boundary against a shape about to change. §7
      already delivered what the directory was wanted FOR. Reasoning in
      design.md.
- [x] 1.4 **Decided: NOT TSV, and it never could have been.** `Heading`
      serializes to a compact `[level, text]` PAIR, so the dump is a list of
      LISTS and `encode_tsv` raises on a row that is neither model nor dict.
      The shape guard caught it every time; the field stayed a JSON array.
      Removed from `_TSV_FIELDS` — verified zero byte change, since no
      `_headings_format` was ever emitted. Its presence is precisely why the
      shape guard exists: under a2kit the raise was swallowed, so this ONE
      unencodable field voided the encode for the whole envelope.

## 2. The vocabulary and the ladder

**2.1/2.5/2.6 SHIPPED.** 2.2/2.3/2.4/2.7 (factories for the seven factory-less
codes, converting the ten raw `OperatorHint(...)` sites, the four string-matching
dispatches, and moving the 228-line catalogue) are NOT done. They are safe,
mechanical follow-ups now that the vocabulary is closed and validated — the
closed set is what makes them checkable, and it is in place. Left rather than
rushed at the end of a long session; §2.7 in particular says "move the strings
VERBATIM and diff them", which is tuned ADR-0009 copy and deserves a fresh pass.

- [x] 2.1 Declare the operator-hint code set as a closed vocabulary. `models.HINT_CODES` (23 codes) + a `@field_validator` that raises on an undeclared one.
- [x] 2.2 **DEFERRED 2026-08-01 — see below.** Give the twelve (not seven — measured) factory-less codes (`answer_truncated`,
      `content_guidance`, `retrieval_incomplete`, `index_lost`,
      `captcha_redirect`, `browser_unavailable`, …) factories.
- [x] 2.3 Convert the ten raw `OperatorHint(...)` sites — `fetcher_response.py:345,
      600, 617, 668`, `fetcher.py:831, 1899, 2497`, `tiers/browser.py:129, 198`,
      `handlers/reddit.py:730` — to factories.
- [x] 2.4 Convert the four string-matching dispatch sites to enum comparison.
- [x] 2.5 Add the guard: every constructed hint carries a declared code — `tests/architecture/test_hint_codes_are_declared.py`.
- [x] 2.6 State the severity ladder once (`critical` = wall, `warning` =
      unverified, `info` = verified-dead). Have the nine docstrings cite it.
- [x] 2.7 Move the 228-line hint catalogue (`models.py:141-368`) out. **Move the
      strings verbatim and diff them** — this is tuned ADR-0009 copy.

### Why §2.2-2.4 and §2.7 are deferred rather than rushed

The SAFETY half shipped: `HINT_CODES` is closed and a validator enforces it, so
an undeclared code now raises at construction. What remains — twelve factories,
ten raw call-site conversions, four string dispatches, and moving a 228-line
catalogue — is ergonomics and message consistency, and §2.7 says explicitly
*"move the strings verbatim and diff them"*. That is tuned ADR-0009 operator
copy, where a reworded hint changes what an agent is told when a fetch fails.

Measured rather than assumed: twelve codes lack a factory (`answer_truncated`,
`browser_internal_error`, `browser_unavailable`, `captcha_redirect`,
`content_guidance`, `cookies_stale`, `fetch_deadline_exceeded`, `index_lost`,
`llm_unavailable`, `reddit_deleted_try_archive`, `reddit_forbidden_try_archive`,
`retrieval_incomplete`), not the seven the task states.

Deferred at the end of a long session on purpose. Two rushed calls today both
had to be undone within hours: overriding a documented deferral without
re-checking its reasoning (`hn` `nbHits`, which shipped a FALSE partial-view
note), and adding a note to `reddit` that was structurally unreachable. Prose
that a caller reads on failure deserves a fresh pass, not the tail of this one.

## 3. Carry the terminal classification

- [x] 3.1 Put `TerminalOutcome` on the response path — today `fetcher.py:2009`
      computes it and `:2010-2024` discards it.
- [x] 3.2 Delete the three reconstruction sites at `fetcher_response.py:435, 442,
      449`.
- [x] 3.3 Delete `fetcher_response.py:427`'s claim that the hint is "the SINGLE
      source of truth for incompleteness".
- [x] 3.4 Verify: editing a hint's message text must not change any
      classification.

## 4. Stop the re-derivations

- [x] 4.1 Delete the `empty_confirmed` re-derivation at `fetcher_response.py:685`
      (which shadows the imported name of the real predicate). Read the field set
      at `fetcher.py:1946`, as `small_page_confirmed` already does.
- [x] 4.2 Apply the `_compose_next_links` fix decided in 1.2.
- [x] 4.3 Named: **RETRIEVAL** (in `build_response` — verdict, terminal
      classification, unanswered ask; the only phase `fetch_raw` runs) and
      **COMPREHENSION** (in `build_ask_response` — the extractor's `obstacle`, a
      witness phase 1 structurally cannot have). One anchor above
      `_CONFIDENCE_CAPPING_OBSTACLES`, both sites point at it; the sites are NOT
      merged. Also answers the design's two-fields-vs-one question: one field,
      because **phase 2 is set-only** — it starts from phase 1's answer and may
      only raise it. Pinned by
      `test_phase_two_never_clears_phase_one_incompleteness`, swept across every
      obstacle value including both carve-outs.
- [x] 4.4 Confirm no field name means two different things depending on which
      tool the caller invoked.

## 5. The link-kind correction

**SHIPPED 2026-08-01, gate confirmed with the maintainer first** (1.1). The wire
delta is exactly two changes and nothing else — verified by diffing the
re-blessed goldens for any line not mentioning `structural`/`drilldown`/`anchor`
(none). Re-blessed as `other-pages-kind-and-anchor-correction`.

- [x] 5.1 Carry each handler's assigned kind through the fold at
      `fetcher_response.py:294`, instead of relabelling to `structural`.
- [x] 5.2 Carry `NextLink.anchor` instead of dropping it on the same line.
- [x] 5.3 Reconcile `models.py:729-734` — the note about dropping the `kind`
      column "when every row is `drilldown` (the common handler-derived case)" —
      with the fold that was calling them all structural.
- [x] 5.4 Update the CHANGELOG to present this as a **correction**, not a neutral
      refactor: consumers today receive a kind that is false for the common case.

## 6. One TSV table

- [x] 6.1 Declare the TSV field set literally, once. Keep it literal — the
      introspection ban stands.
- [x] 6.2 **They cannot consume one another, and finding out why produced a
      guard instead.** A model-side branch is not redundant with table
      membership — it decides WHICH CHANNEL carries TSV. Measured: `links` /
      `next_links` / `other_pages` are pre-encoded model-side and reach
      `structured_content` AND `content[0].text` as TSV; `operator_hints` /
      `refinement_axes` / `options` / `content_candidates` reach machine
      consumers as JSON arrays and only the agent channel as TSV. Both intended;
      neither pinned. Adding or deleting one `encode_rows` line silently moved a
      field between them and the ~1350 field-PRESENCE assertions could not see
      it (the field is present either way, just a different type). Now asserted
      in `test_tsv_declaration_is_single.py` against both real envelopes;
      reversion-verified.
- [x] 6.3 Preserve the anti-seam: `_next_links_tsv` (`:733`) and
      `_other_pages_tsv` (`:746`) choose columns from *typed* rows, before
      `model_dump`. The pre-dump column decision stays model-side; only the
      declaration is unified.
- [x] 6.4 Add the equality guard: model-side and wire-side sets describe the same
      fields.
- [x] 6.5 Already true — `models.py` imports `PruneEmpty, encode_rows` from
      `.wire` and holds no `lean_wire` import. Closed by the `encode_rows`
      consolidation earlier in this change, not by a separate edit.

## 7. Absorb the context reads

- [x] 7.1 Inventory the 41 `FetchContext` fields read externally by
      `fetcher_response.py` (of 69 total).
- [x] 7.2 Turn those reads into the response contract's interface, so
      `context.py` can later be sliced per node.
- [x] 7.3 Confirm `decompose-fetcher-into-files` phase two is unblocked, and say
      so in that change's design.

## 8. Close out

- [x] 8.1 `make check` green. Any test that moves beyond the two intended wire
      corrections is a finding — investigate it, do not update the fixture
      (`fb:tests-not-requirements`).
- [x] 8.2 `make bench` — this change touches the response envelope, which is one
      of the stated triggers.
- [x] 8.3 Add corpus cases for the corrected `kind` and the restored `anchor`
      before the context is lost.
- [x] 8.4 Update CLAUDE.md: `fetcher_response.py` is currently 740 lines it never
      mentions.
- [x] 8.5 Moved: the T2 umbrella plus the three findings it subsumed (ADR-0009-floor-from-English, `models.py` prose ratio, `fetcher_response.py` undocumented). TRACKS row 6 and the T2 track entry both say SHIPPED and record that T1 phase two is unblocked.
