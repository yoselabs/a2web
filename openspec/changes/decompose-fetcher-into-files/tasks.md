# Tasks

Two phases. **Phase two is blocked on `unify-the-response-contract`.** Do not
start it early — 41 of `FetchContext`'s 69 fields are read externally by
`fetcher_response.py`, and attempting both phases at once turns a decomposition
into a rewrite.

Land nothing in this change except the move, the loop, and the ladder-skip fix
that the loop makes unexpressible. v0.23 is the demonstration of what a refactor
that is also a bug fix costs.

## 1. Before cutting anything

- [ ] 1.1 Read `_escalate_browser:2136-2151` and `_escalate_paid:2236-2253` side
      by side. Confirm the shared tail is a utils leaf and not a third
      escalator's worth of policy. It is the one file in the tree placed by
      judgement rather than census.
- [ ] 1.2 Decide whether the retry signal carries a stage marker or is bare
      (design Open Questions).
- [ ] 1.3 Decide the diagnostics question: append always (browser `:2105`, paid
      `:2210`, tier loop `:1183`) or only-on-success (`_dispatch_archive:899`).
      It is the same divergence class as the install sequence.
- [ ] 1.4 Record the four anti-seams as tests or comments **before** moving, so
      the move cannot quietly cross one:
      - `:1247`'s escalation-win check is correct only because `_install_won_tier`
        at `:1254` has not run yet
      - the three promotion/terminal phases are one mutually-exclusive chain;
        `small_page_promoted()` reads a field written 460 lines away
      - `_phase_extract`'s pre-rendered branch must keep the **ladder call**
        (`:1299-1323` documents the four-consumer starvation)
      - `FetchContext` is phase two only

## 2. Phase one — the install chokepoint

- [ ] 2.1 Define `TierInstall` carrying all six transport fields (`body`,
      `content_type`, `final_url`, `tier_used`, `pre_rendered_payload`,
      `status_code`).
- [ ] 2.2 Write `install(ctx, TierInstall)` as the single write site.
- [ ] 2.3 Convert all five install sites (`:1254`, `:1062`, `:1058`,
      `:2136-2151`, `:2236-2253`) to it.
- [ ] 2.4 Verify `_install_gate_archive` now sets `status_code` — it does not
      today.
- [ ] 2.5 Retire `_install_rendered_fields`' exclusion of the transport half
      (`:1279-1281`) and update its docstring, which currently confesses the
      content-half history.

## 3. Phase one — the loop

- [ ] 3.1 Change escalation to **return a retry signal** instead of calling
      comprehension forward — archive, browser, paid.
- [ ] 3.2 Establish the single path: retrieval → comprehension → sufficiency,
      with one loop head.
- [ ] 3.3 Verify the archive-post-gate ladder skip (`fetcher.py:1058`) is now
      unexpressible, not merely fixed. It is the fifth copy of a bug repaired one
      path at a time four times.
- [ ] 3.4 Delete `_phase_listing_render:2716-2722`'s inline assess-and-set — it
      exists only because there was no loop head to return to.
- [ ] 3.5 Make `_phase_extract_answer` non-re-entrant. It is currently entered 3×
      and is not idempotent — *answer* is being used as the loop body.
- [ ] 3.6 Confirm the `retrieval → comprehension` import cycle is gone. The cycle
      was the loop; if it survives, the loop was not modelled.
- [ ] 3.7 Resolve the paid budget explicitly rather than by call order across
      four competitors.

## 4. Phase one — the tree

- [ ] 4.1 `fetcher.py` → `fetcher/` per the design's tree. `FetchContext` stays
      whole in `context.py`.
- [ ] 4.2 Split `retrieval/`: `cache`, `conditional` (the 304 path, out of
      tier_walk), `cookies`, `proxy_lease` (out of tier_walk), `tier_walk`,
      `install`, `escalate/`.
- [ ] 4.3 Split `comprehension/`: `prerendered` and `json_synth` out of the
      ladder; `ladder`, `gate`, `menu`.
- [ ] 4.4 Create `sufficiency/completeness.py` — the question has no name today.
- [ ] 4.5 Split `answer/`: `digest`, `prompt_call` and `obstacle` out of extract,
      `links`.
- [ ] 4.6 Create `verdict/` with the promotion chain and terminal **together** —
      they are mutually exclusive by early return and must not be separated.
- [ ] 4.7 Confirm no file exceeds 300 lines. Largest expected is `context.py` at
      281, then `menu.py` at 191.

## 5. Phase one — the residual-ordering guard

- [ ] 5.1 Write the **one architecture test** covering the hazards the rejected
      Stage protocol would have made unexpressible: the paid budget resolved by
      call order, `fc.record_count` never resetting (`:1725-1732`, no
      `else: None`), `_install_gate_archive` not setting `status_code`.
- [ ] 5.2 Assert it is non-vacuous — it must be observed failing.
- [ ] 5.3 **If this test proves hard to write, reopen the Stage-protocol
      decision** rather than skipping the test and living with the convention.
      That is the tripwire the design committed to.

## 6. Phase one — close out

- [ ] 6.1 `make check` green. Any behaviour change other than the ladder-skip fix
      is a defect in the move.
- [ ] 6.2 `make bench` — tier routing and escalation are stated triggers.
- [ ] 6.3 Add a corpus case for the archive-post-gate path producing
      `content_candidates` / `other_pages` / `record_count`, which it does not
      today.
- [ ] 6.4 Update CLAUDE.md's pipeline description — it says `_run_pipeline` is "a
      12-line coordinator calling six named phases"; it is 47 lines calling
      twelve, and `_phase_cache_write` is not terminal.
- [ ] 6.5 Confirm the growth curve claim can now be tested: record the line
      counts so a future scan can tell whether the seam held.

## 7. Phase two — BLOCKED on `unify-the-response-contract`

- [ ] 7.1 Confirm that change has landed and absorbed the 41 external
      `FetchContext` reads.
- [ ] 7.2 Slice `context.py` per node.
- [ ] 7.3 Update the ~19 test modules importing `FetchContext`.
- [ ] 7.4 Move the T1 entries to `BACKLOG-CLOSED.md`, including the two subsumed
      ones (*no "install a fetch result" type*, *five escalation decisions live
      outside the single policy function*) and *the sufficiency question has no
      name*.
