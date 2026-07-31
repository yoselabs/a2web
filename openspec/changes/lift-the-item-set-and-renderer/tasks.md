# Tasks

Split the live fix from the lift. Section 1 ships on its own, first — a product
hole should not wait on a refactor, and shipping it first puts the witness in
place before the code moves.

## 1. The live ADR-0015 hole — ship this first, alone

**SHIPPED 2026-08-01, ahead of the rest of this change**, as the section said
to. Two notes for the lift that follows:

- 1.1/1.2 were done by converging both paths on `RecordSet`, NOT by deriving
  `next_links` and `options` separately for JSON-LD. `_records_to_next_links`
  and `_records_to_options` apply unchanged, which is what makes 1.4's
  equivalence witness meaningful rather than a comparison of two derivations
  that could drift apart unobserved.
- The fix is strictly ADDITIVE: the DOM miner keeps precedence wherever it
  produces a set, so no page that already shipped an index sees it change.
  `test_dom_records_keep_precedence_when_both_exist` pins that, and the lift
  must preserve it.
- `_escalate_via_json` now RETURNS the record set rather than writing it onto
  `fc` — the first draft mutated the context and broke the purity contract that
  `test_menu_assembly_is_pure` exists to hold.

- [x] 1.1 Derive `next_links` from the JSON-LD `ItemList` path
      (`domain.py:433`), as the DOM record-miner path does at
      `fetcher.py:1788`.
- [x] 1.2 Derive `options` from the same path, as `fetcher_response.py:234` does
      for mined records.
- [x] 1.3 Add a corpus case: a listing page whose items live in `ItemList`
      JSON-LD must ship a populated `other_pages`. Phrase the criteria against
      stable structural facts.
- [x] 1.4 Verify a page reachable by both paths produces the same index either
      way. This is the witness the lift will be checked against — write it now,
      not after.
- [x] 1.5 CHANGELOG: this is an envelope change for JSON-LD listing pages, and a
      correction.

## 2. One cap, and the baseline that pins the violation

- [ ] 2.1 Declare the onward-link cap once. `openspec/specs/link-discovery/spec.md:37`
      states one invariant; `arxiv.py:317`, `hn.py:169`, `reddit.py:612` and
      `wikipedia._WIKILINK_CAP` implement it four times.
- [ ] 2.2 Correct `discourse.py:227` from 50 to the declared cap.
- [ ] 2.3 Correct `handler_probe.py:177` in the **same commit** — it records
      "observed 30" as healthy and currently pins the violation green. Say in the
      commit message that the baseline was recording a defect as health.
- [ ] 2.4 Add the guard: no emitting site holds its own literal.

## 3. Cap-and-declare

- [ ] 3.1 Port `arxiv.py:297`'s `N of M` + partial-view note to `hn.py`,
      `discourse.py`, and `reddit.py` listings, which truncate silently today.
- [ ] 3.2 Carry the source-reported total where one exists — `hn` and `v2ex`
      already hold it and discard it.
- [ ] 3.3 Confirm no capped set reaches the wire without declaring truncation.

## 4. The item set converges

- [ ] 4.1 Choose the single representation. `record_mine.RecordSet` is the
      closest existing shape.
- [ ] 4.2 Converge the seven-plus sources onto it: `fetcher.py:1723`, JSON-LD
      `domain.py:433`, `hn.py:125,160`, `discourse.py:196-244`,
      `arxiv.py:262,311`, `reddit.py:562,610`, GitHub/Wikipedia candidates-only.
- [ ] 4.3 Write the four operations once — render, derive-next-links,
      cap-and-declare, project-to-wire.
- [ ] 4.4 Decide whether project-to-wire can live with the other three; the
      renderer is pure and the wire projection is domain-coupled (design Open
      Questions).
- [ ] 4.5 Reconcile the markdown caps: 30/50/25/25 across sites today.

## 5. Lift the renderer out of `domain.py`

- [ ] 5.1 Confirm the Ask First gate — promoting to `packages/` is on the list,
      and boundary types need design.
- [ ] 5.2 Resolve divergence one **during** the move: delete
      `_opengraph_to_markdown:531`'s hand-rolled table, use `_rows_to_md_table`.
      Pick one cap pair deliberately (200/50 vs 80/none) and record the choice.
- [ ] 5.3 Resolve divergence two: `_single_entity_md:345` is default-keep and
      argues an allowlist "silently loses an unanticipated answer-bearing field";
      `_recipe_md:316` is that allowlist. Decide which is right and record the
      reason — this decides what a recipe page silently drops.
- [ ] 5.4 Resolve divergence three: name the three bare `50`s (`:285`, `:439`,
      `:548`), one of which carries a documented manual-sync comment. Do not
      carry a manual sync across a package boundary.
- [ ] 5.5 Move `:188-551` + `json_response_fallback` to `packages/`. It has zero
      a2web imports and four test files already treat it as a unit.
- [ ] 5.6 Update the two consumers: `fetcher.py:1346`, `:1689`.

## 6. What stays behind

- [ ] 6.1 Confirm `domain.py` is ~120 lines and its docstring is now true —
      "pure functions reading `AppSettings` or models but too small to deserve
      their own module" currently describes 12 of 551 lines.
- [ ] 6.2 **Do not move `is_search_shaped`.** `:36-37` states it gates
      `actions.empty.is_confirmed_empty` (`empty.py:70`) — one clause of the
      ADR-level empty→ok conjunction.
- [ ] 6.3 **Do not separate `_CAPTCHA_SEARCH_HOSTS` (`:77-84`) from
      `packages/block_detector.py:186-190, 305-307`.** Two halves of one
      Google/Bing policy, linked by comment only. Add the test over the pair —
      nothing tests it today and this is the moment.
- [ ] 6.4 Fix `__all__`: drop `parse_query_params` (zero call sites in `src/`,
      6 tests, documented at length) or find it a caller; add
      `strip_reader_prefix`, which `fetcher.py:56` imports today.

## 7. Close out

- [ ] 7.1 `make check` green. `tach check` must accept the new package.
- [ ] 7.2 `make bench` — this touches `next_links` and listing output, both
      stated triggers.
- [ ] 7.3 Confirm `tests/architecture/test_tach_covers_every_package.py` sees the
      new package. An unlisted package silently gets no contract at all.
- [ ] 7.4 Move the Row 1 / Row 2 entries and the discourse cap entry to
      `BACKLOG-CLOSED.md`. Leave handler page-rendering open — it is the larger
      shape and wants the item set to exist first.
