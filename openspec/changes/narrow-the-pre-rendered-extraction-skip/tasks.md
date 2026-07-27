# Tasks

## 1. Prove the boundary before moving it

- [ ] 1.1 Failing test: a pre-rendered fetch of listing-shaped HTML yields a
      `record_synth` candidate in `fc.content_candidates`. MUST fail today.
- [ ] 1.2 Failing test: the same fetch yields a non-`None` `_build_link_digest`.
      MUST fail today, and MUST fail for the gate reason — assert the links are
      already present, so the test distinguishes this defect from the one the
      previous change fixed.
- [ ] 1.3 Failing test: `fc.record_count` is set and commensurate with the
      fixture's known item count. A known count is the non-vacuity floor;
      "not None" passes on one stray record. MUST fail today.
- [ ] 1.4 Passing-today test in the same file: the fetch emits NO `extract`
      diagnostic row. This one starts green and must STAY green — it is the half
      of the boundary that must not move (D4).
- [ ] 1.5 Record all four outcomes in the commit message. Three watched failing,
      one watched passing.

## 2. Narrow the skip (D1)

- [ ] 2.1 `_phase_extract`'s pre-rendered branch: after the five field copies,
      `await _run_extraction_escalation(fc, raw_html=raw_html)` then
      `_phase_listing_completeness(fc, raw_html=raw_html)`, then return.
- [ ] 2.2 Confirm the baseline candidate seeds from `fc.content_md` with no new
      branch — the escalation already reads it. If it does not, STOP: the
      premise of D1 is wrong and the design needs revisiting, not a workaround.
- [ ] 2.3 Confirm `extract_markdown`, `parse_metadata` and the date finders are
      still NOT called on this path.
- [ ] 2.4 Confirm 1.1-1.3 pass and 1.4 is still green.

## 3. Gate

- [ ] 3.1 `make check` green, coverage ≥85%.
- [ ] 3.2 `make arch` green; `uv run tach check` clean.
- [ ] 3.3 Every new guard watched failing (task 1) and carrying a non-vacuity
      assertion.
- [ ] 3.4 Check the existing suite for tests that asserted the OLD behaviour —
      a test pinning "no candidates on the pre-rendered path" is now wrong and
      must be corrected, not deleted. Name any found.

## 4. Measure the cost this change is gated on (D3)

- [ ] 4.1 Time the two rungs over a pre-rendered body on each shape: browser DOM,
      archive HTML, a JSON handler payload, jina markdown. The JSON and markdown
      cases are pure waste by construction — establish how much.
- [ ] 4.2 If the no-op cost is material on the non-HTML bodies, add the
      precondition INSIDE the rung, where the rest of its gating lives — never as
      an outer content-type gate (D3). If it is not material, say so with the
      numbers and add nothing.

## 5. Evidence — the live run

- [ ] 5.1 Re-run the exact subset that measured the last attempt failing:
      `--only listing --axis next_links --mode detail` on a subscription
      provider (ADR-0016). `listing-answer-always-leaves-an-index` and
      `reddit-listing` MUST move from `unscored` to `scored`. If they do not,
      this change has the same status as the last one and MUST NOT be archived
      as delivering its outcome.
- [ ] 5.2 Full-corpus `make bench` for the token and latency delta.
- [ ] 5.3 Write `eval/findings_<date>.md`. State that `other_pages` quality on
      browser-served pages is a FIRST observation — the axis has one prior data
      point ever (mean 3.17, 2026-07-28) and none on this population. Poor first
      numbers are a baseline, not a regression.
- [ ] 5.4 Report `listing_partial` firing where it never has. Expect it to look
      like a regression in any metric counting `ok` verdicts; it is the
      capability working.
- [ ] 5.5 Record, do not fix, whatever the newly-reachable index and sufficiency
      signals surface.

## 6. Close the loop

- [ ] 6.1 `restore-links-on-pre-rendered-tiers`: its tasks 6.1-6.4 are blocked on
      this change. Once 5.1 passes, close them out against THIS run and archive
      that change with an explicit note that its stated outcome required a second
      change — do not let the archive read as though it delivered alone.
- [ ] 6.2 BACKLOG: retire the "NEXT — the digest gate blocks every pre-rendered
      page" entry, replacing it with the resolved answer (the gate was right; the
      skip was over-scoped) so the next reader does not re-open it.
- [ ] 6.3 BACKLOG: record the `source="trafilatura"` label inaccuracy on the
      pre-rendered path (D1), and the two spec requirements that described a
      deleted `tier_extras` field for months without anything noticing — the
      latter is a candidate for the same class of guard as the CLAUDE.md
      staleness found by `close-silent-enforcement-loss`.
