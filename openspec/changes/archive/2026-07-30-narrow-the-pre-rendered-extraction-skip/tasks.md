# Tasks

## 1. Prove the boundary before moving it

- [x] 1.1 Failing test: a pre-rendered fetch of listing-shaped HTML yields a
      `record_synth` candidate in `fc.content_candidates`. MUST fail today.
- [x] 1.2 Failing test: the same fetch yields a non-`None` `_build_link_digest`.
      MUST fail today, and MUST fail for the gate reason — assert the links are
      already present, so the test distinguishes this defect from the one the
      previous change fixed.
- [x] 1.3 Failing test: `fc.record_count` is set and commensurate with the
      fixture's known item count. A known count is the non-vacuity floor;
      "not None" passes on one stray record. MUST fail today.
- [x] 1.4 Passing-today test in the same file: the fetch emits NO `extract`
      diagnostic row. This one starts green and must STAY green — it is the half
      of the boundary that must not move (D4).
- [x] 1.5 Record all four outcomes in the commit message. Three watched failing,
      one watched passing.

## 2. Narrow the skip (D1)

- [x] 2.1 `_phase_extract`'s pre-rendered branch: after the five field copies,
      `await _run_extraction_escalation(fc, raw_html=raw_html)` then
      `_phase_listing_completeness(fc, raw_html=raw_html)`, then return.
- [x] 2.2 Confirm the baseline candidate seeds from `fc.content_md` with no new
      branch — the escalation already reads it. If it does not, STOP: the
      premise of D1 is wrong and the design needs revisiting, not a workaround.
- [x] 2.3 Confirm `extract_markdown`, `parse_metadata` and the date finders are
      still NOT called on this path.
- [x] 2.4 Confirm 1.1-1.3 pass and 1.4 is still green.

## 3. Gate

- [x] 3.1 `make check` green, coverage ≥85%.
- [x] 3.2 `make arch` green; `uv run tach check` clean.
- [x] 3.3 Every new guard watched failing (task 1) and carrying a non-vacuity
      assertion.
- [x] 3.4 Check the existing suite for tests that asserted the OLD behaviour —
      a test pinning "no candidates on the pre-rendered path" is now wrong and
      must be corrected, not deleted. Name any found.

## 4. Measure the cost this change is gated on (D3)

- [x] 4.1 Time the two rungs over a pre-rendered body on each shape: browser DOM,
      archive HTML, a JSON handler payload, jina markdown. The JSON and markdown
      cases are pure waste by construction — establish how much.
- [x] 4.2 If the no-op cost is material on the non-HTML bodies, add the
      precondition INSIDE the rung, where the rest of its gating lives — never as
      an outer content-type gate (D3). If it is not material, say so with the
      numbers and add nothing.

## 5. Evidence — the live run

- [x] 5.1 **FAILED — criterion not met, for the third round running.** Both
      cells still `unscored` (`eval/runs/post-ladder-fix`,
      `eval/runs/post-install-fix`). Per this task's own terms, this change MUST
      NOT be archived as delivering its outcome. Cause found and recorded: a
      THIRD blocker, per page — neither yields a structured candidate, so the
      digest gate correctly declines. Probe on arxiv: `records=None`,
      `0` JSON payloads, `links=484`, `digest=None`.
- [x] 5.2 Full-corpus `make bench` for the token and latency delta.
- [x] 5.3 Write `eval/findings_<date>.md`. State that `other_pages` quality on
      browser-served pages is a FIRST observation — the axis has one prior data
      point ever (mean 3.17, 2026-07-28) and none on this population. Poor first
      numbers are a baseline, not a regression.
- [x] 5.4 Report `listing_partial` firing where it never has. Expect it to look
      like a regression in any metric counting `ok` verdicts; it is the
      capability working.
- [x] 5.5 Record, do not fix, whatever the newly-reachable index and sufficiency
      signals surface.

      **MEASURED 2026-07-28 from the full-corpus run** (`eval/runs/2026-07-28_full`,
      114 cells) — no new spend; this is the run `close-silent-eval-loss` 8.1b
      commissioned. The answer is SPLIT, and both halves matter:

        listing-answer-always-leaves-an-index   unscored -> SCORED
                                                  a2web_detail  next_links 4
                                                  a2web_extract next_links 3
        reddit-listing                          STILL unscored
                                                  "system produced no candidate
                                                   block" on BOTH systems

      So `other_pages` is now reachable on the arXiv-listing cell — the claim
      this change originally made and then had to retract is TRUE for that cell
      after the later changes landed. It is NOT true for `reddit-listing`, which
      still emits no index at all despite scoring quality 5. One cell moving is
      not the population moving; do not restate the retracted claim.

      **New, recorded not fixed** (task 6.4 / 5.5): `listing-answer-always-leaves-an-index`
      scored quality **0** on `a2web_extract` while its `next_links` scored 3.
      The judge: "a prose summary of paper topics with no structured index, no
      links or identifiers to individual entries, and no actionable pointers."
      The index exists in `other_pages` but the ANSWER points at nothing — so
      the two axes disagree about the same cell. Either the answer must reference
      the index it shipped, or the quality rubric is reading a channel the
      envelope deliberately separates. Worth deciding before either is called a
      regression.

## 6. Close the loop

- [x] 6.1 UNBLOCKED and resolved 2026-07-28. The correction this task demanded
      is already in `restore-links-on-pre-rendered-tiers/proposal.md` as an
      in-place CORRECTION block, so that change is safe to archive on this count.

      A THIRD measurement (full-corpus run) refines the picture rather than
      repeating the retraction: `listing-answer-always-leaves-an-index` moved
      `unscored -> scored` (next_links 4 / 3), so `other_pages` IS reachable
      there now — but `reddit-listing` still emits no candidate block at all.
      One cell is not the population. The retracted claim stays retracted; what
      is now true is narrower and is stated as such in both task files.
- [x] 6.2 BACKLOG: retire the "NEXT — the digest gate blocks every pre-rendered
      page" entry, replacing it with the resolved answer (the gate was right; the
      skip was over-scoped) so the next reader does not re-open it.
- [x] 6.3 BACKLOG: record the `source="trafilatura"` label inaccuracy on the
      pre-rendered path (D1), and the two spec requirements that described a
      deleted `tier_extras` field for months without anything noticing — the
      latter is a candidate for the same class of guard as the CLAUDE.md
      staleness found by `close-silent-enforcement-loss`.

## 7. What task 1 could not have found — the install paths (added mid-change)

The narrowing in task 2 was correct and insufficient, for a reason the task
list did not anticipate. `Rendered`'s fields were copied onto the context in
**four** places, not one:

    _phase_extract          the tier WON the loop
    _dispatch_archive       archive dispatched out-of-band
    _escalate_browser       the gate said escalate
    _escalate_paid          ditto, paid rung

`restore-links-on-pre-rendered-tiers` added `links` to exactly one of them, so
its fix was a no-op on every page reaching the browser by ESCALATION — a
handler wins, the gate says `length_floor`, the browser escalates — which is
the common path, not the rare one. Measured on `arxiv.org/list/cs.CL/recent`
AFTER that change shipped: `fc.links == 0`.

Its guard could not see this: it tested the extraction seam, not the install.

- [x] 7.1 Collapse all four copies into one `_install_rendered_fields(fc, pre)`.
      Transport fields stay at their call sites — the escalation paths must set
      them from their own tier result.
- [x] 7.2 Guard the single copy structurally (a block of ≥3 `Rendered`-field
      assignments outside the helper is a fifth copy being born). Watched biting
      on a reintroduced copy, not merely watched green. `extract_result` is
      exempt WITH a stated reason — a different type carrying `published`, which
      `Rendered` has no field for.
- [x] 7.3 Re-probe: `fc.links` on the arxiv escalation path is 0 → 484.

## 8. The third blocker — recorded, deliberately not fixed

- [x] 8.1 SUPERSEDED — do NOT open this change. Its premise ("arXiv's handler
      has had a correct index at tier 0 the whole time, on a path that throws it
      away") was retired as WRONG in BACKLOG the same day it was filed: run
      rather than read, the handler returned `next_links: 0` and 40 chars of
      markdown, so nothing correct was being discarded.

      It is now moot for a second, independent reason. `handler-parses-nothing-is-not-success`
      fixed the arXiv parser, so the handler WINS the tier loop (probe:
      `ok (5910 chars, 10 candidates)`) and never reaches the browser escalation
      whose discard was the alleged defect. The "losing tier's structured output"
      path needs a handler that actually loses; arXiv is no longer one.

      If the discard-vs-merge question is real it needs a fresh example and its
      own evidence — not this one, which was wrong twice over.
