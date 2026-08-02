# Tasks

Two phases. **Phase two is blocked on `unify-the-response-contract`.** Do not
start it early — 41 of `FetchContext`'s 69 fields are read externally by
`fetcher_response.py`, and attempting both phases at once turns a decomposition
into a rewrite.

Land nothing in this change except the move, the loop, and the ladder-skip fix
that the loop makes unexpressible. v0.23 is the demonstration of what a refactor
that is also a bug fix costs.

## 1. Before cutting anything — DONE 2026-08-02

> **Every line number in this change is stale.** It was written against a
> 2771-line `fetcher.py`; the file is **3018** lines today, and
> `unify-escalation-executor` has since landed `_dispatch_action`, which
> collapsed part of the install table. Re-derive before cutting — the citations
> below are the re-derived ones. The growth in the interval (+247 lines in two
> days, through a change that touched it only incidentally) is itself evidence
> for the proposal's central claim.

- [x] 1.1 **Read side by side. It IS a utils leaf — and the census would have
      merged two things that must not merge.** The shared tail is
      `install → optional ladder → re-gate`, byte-similar across
      `_escalate_browser:2356-2371` and `_escalate_paid:2462-2479`. Two
      differences, and both are real:
      **(a) paid observes its own success, browser does not.** Paid appends
      `tier_outcome(source, verdict=ok)`; browser appends NO observation on a
      successful render (it observes only `subresource_blocks > 0`, or
      `not_found`/`paywall` on failure). That asymmetry is load-bearing in a
      direction worth stating: `is_confirmed_empty` requires an independent
      browser render, and the browser's success leaves the decision log with no
      `tier_outcome` from it at all.
      **(b) the ladder guard differs.** Browser decodes any non-empty body;
      paid requires `"html" in content_type`, because a markdown-native paid
      tier (Firecrawl) returns clean markdown that the ladder must not touch.
      The paid predicate is the correct general one — browser's is equivalent
      only because a browser body is always HTML.
      So the leaf takes the install and the re-gate; the observation and the
      html-guard are **parameters**, not shared code. A census merge would have
      silently given the browser paid's `observe` (changing what
      `is_confirmed_empty` sees) or given paid browser's guard (running the
      ladder over Firecrawl's markdown).
- [x] 1.2 **Decided: bare signal.** The design leaned that way; the code agrees
      more strongly than the design knew. `_dispatch_action` already returns a
      bare 3-member `_Exec` (`CONTINUE`/`RESTART`/`STOP`) and the tier loop
      already consumes it as pure control flow — a stage marker would be a
      SECOND control vocabulary alongside one that works. And the marker's only
      customer would be "which stage to resume at", which is precisely the
      freedom the loop exists to remove: if a caller can name its resume point,
      a stage can still be skipped, and H1 is back with a nicer spelling.
      Bare signal plus the existing context state; `_Exec` is the precedent to
      extend, not to duplicate.
- [x] 1.3 **Decided: append always — and the only-on-success justification is
      provably stale.** `_dispatch_archive:966-972`'s docstring says a failed
      escalation "should not displace the originating verdict". It cannot:
      **`resolve_verdict` reads `Observation`s, not `Diagnostic`s** (verified —
      `decision_log.py:119` filters `ObservationKind`), and verdict became a
      pure projection of the decision log in v0.23. A `Diagnostic` has no path
      into verdict resolution at all, so the reason the divergence exists
      stopped being true and nothing noticed.
      What it costs today is ADR-0009 visibility: a failed archive dispatch
      leaves no row, so the response cannot show archive was tried and did not
      help — the caller sees a gap where an attempt was.
      **NOT applied here.** Adding rows changes `diagnostics_summary` prose,
      which is a behaviour change, and this change's rule is that the only
      behaviour change is the ladder skip (D7). Filed in `BACKLOG.md` so the
      decision does not have to be re-derived.
- [x] 1.4 **Recorded as a test, not a comment** —
      `tests/architecture/test_fetcher_phase_ordering.py`, registered in
      `docs/architecture/README.md`, and **all four reversion-verified** (each
      probe applied to `fetcher.py`, observed failing, reverted).
      It indexes functions by NAME across the whole fetcher tree, resolving
      either today's `fetcher.py` or tomorrow's `fetcher/` package, and
      deliberately does NOT resolve through an import: an import-based guard
      goes quiet the moment a function lands in a module that is no longer
      re-exported, which is exactly the window this move opens. A rename fails
      the guard rather than skipping it.
      The four:
      - the escalation-win check reads `fc.tier_used` (now `:1353`) and is
        correct only because `_install_won_tier` (now `:1360`) has not run —
        above the install it means "an out-of-band escalation won", below it
        means "any tier won", and the loop returns without installing
      - `_apply_terminal` must follow both promotions AND the answer
        (`small_page_promoted()` reads whether extraction produced one), and
        must be called by the COORDINATOR, not `_run_phases`, so the floor also
        runs on the `DeadlineExceeded` path
      - `_phase_extract`'s pre-rendered branch must keep the ladder call **and**
        the sufficiency call *before every `return`* — the 2026-07-28 defect was
        not a missing call, it was a call sitting textually below an early
        return
      - `FetchContext` is phase two; recorded as scope, not as a test — a move
        cannot cross it, only a later task can
      Added a fifth, out of the design's list and marked as such: every
      escalation that installs content must re-gate. It is the invariant the
      loop restructure is meant to make structural, pinned so the move cannot
      lose it in transit — and it carries an instruction to DELETE it with a
      note once the loop makes it redundant, rather than leave it as decoration.

**Measured while doing this, and it sharpens both defects.** The proposal's
install table describes the WRITE sites; the sharper table is what each path
runs afterwards:

| path | extraction ladder | sufficiency |
|---|---|---|
| tier-loop win → `_phase_extract` | yes | yes |
| archive pre-gate → `_phase_extract` | yes | yes |
| **archive post-gate** (`_dispatch_action:1161-1165`) | **no** | **no** |
| browser escalation (`:2370`) | yes | **no** |
| paid escalation (`:2478`) | yes | **no** |

Defect 1 (the fifth copy of the ladder skip) and H1 (escalators skip
sufficiency) are the same table read down two columns — which is the proposal's
claim, now measured against the current file rather than the one it was written
against.

## 2. Phase one — the install chokepoint — DONE 2026-08-02

- [x] 2.1 `TierInstall` is a frozen slotted dataclass carrying the six transport
      fields plus one flag. **Deliberately NOT carrying the rest.** `etag` /
      `last_modified` (tier loop only — response headers no escalation has), the
      archive snapshot dates, and a handler's measured counts stay at their
      sites, because folding them in would force `install` to invent a CLEARING
      semantics: `TierInstall(etag=None)` from the browser path would erase a
      conditional-request token acquired upstream. A chokepoint for the
      duplicated set is a chokepoint; a chokepoint for every field a tier
      touches is a god-setter that must then re-grow presence guards.
      The flag is `post_extract: bool`, and it makes design D6's
      "pipeline-region divergence" a stated field instead of a property of which
      function you happened to call. Pre-extract installs put the body down and
      let extraction fill the content half; post-extract installs have nothing
      downstream to fill it, so `install` calls `_install_rendered_fields`
      itself. The two halves come from one call at the three post-extract sites.
- [x] 2.2 `install(fc, ti)` is the single write site.
- [x] 2.3 All five converted. Line numbers re-derived (the cited ones were from
      the 2771-line file): `_install_won_tier`, `_install_archive_payload`,
      `_install_gate_archive`, `_escalate_browser`, `_escalate_paid`.
      One dead write fell out: `_install_won_tier` was assigning
      `pre_rendered_payload` twice.
- [x] 2.4 **It does now — and the honest report is that the omission was INERT.**
      `fc.status_code` has exactly ONE reader in the whole tree
      (`_phase_cache_write`'s cache-row column), and cache_write declines archive
      results outright, so the missing write could not be observed today. This is
      a trap disarmed, not a bug fixed: the path was one cacheable-archive
      decision away from writing a foreign tier's status into the cache row, and
      its pre-gate sibling `_install_archive_payload` always set it — two archive
      paths disagreeing for no reason anybody chose.
      Said plainly because the alternative is to bank an unearned bug fix: the
      chokepoint's value here is that the divergence is now unexpressible, not
      that a live defect was repaired.
- [x] 2.5 Retired. The docstring no longer says the transport fields are
      "deliberately NOT here" — it says WHY the split survives at all, which is
      that `_phase_extract` still calls `_install_rendered_fields` alone: on the
      pre-extract path the transport fields are already down and extraction only
      fills the content.
- [x] 2.6 **Added, unplanned: `tests/architecture/test_transport_install_chokepoint.py`.**
      The collapse is worth nothing if a sixth writer can appear — that is
      exactly how the content half got four copies, and its guard could not see
      it because it tested the extraction seam rather than the install.
      Three tests: only `install` writes the set; `install` writes EVERY field
      `TierInstall` declares (a declared-but-unassigned field is worse than an
      absent one — the caller passes it, reads the type as the contract, and the
      value goes nowhere); and every exemption still writes something, so a
      stale entry cannot silently pre-authorise the next function to take that
      name. Both behavioural tests reversion-verified.
      **The guard found a sixth writer on its first run**, which is the argument
      for having it: `_dispatch_action`'s `RewriteUrl` branch writes `final_url`
      — legitimately, because there it means "where we are about to look" rather
      than "where a tier landed" — and nothing named it. Three exemptions total,
      each with its reason: the URL rewrite, the conditional-304 cache reuse (no
      tier result exists to install, and `status_code = 200` is a logical hit
      rather than anything a server said), and `_phase_extract`'s JSON-body
      synthesis.

## 3. Phase one — the loop

- [x] 3.1 **Done — the signal is a `bool`, and that is the whole vocabulary.**
      Each rung dispatcher (`_escalate_browser`, `_escalate_paid`, the new
      `_escalate_archive_post_gate`) returns whether it installed content, and
      returns *only* that. Per §1.2's decision the signal is bare: "installed"
      is all any caller needs, and anything richer would let a caller name its
      own resume point, which is the freedom the loop exists to remove.
- [x] 3.2 **The loop head is `escalate(fc, rung, *, state, scroll)`** — dispatch,
      then, if anything landed, `_comprehend(fc)`. Five call sites now go through
      it: the planner's three actions in `_dispatch_action`, the
      `render_requested` block's paid-then-browser ladder, `_phase_obstacle_render`,
      and both rungs of `_phase_listing_render`.
      `_comprehend` reads `fc` rather than taking the tier result, which is the
      load-bearing detail: it **cannot be handed a subset of what was installed**,
      and a subset is exactly what each escalator was passing itself.
      Two implementation notes worth keeping.
      **The html guard is the paid tier's, deliberately.** Browser decoded any
      non-empty body — equivalent only because a browser body is always HTML;
      paid requires `"html" in content_type` because a markdown-native paid tier
      (Firecrawl) returns clean markdown the ladder must not touch. §1.1 flagged
      this; unifying on the browser's predicate would have run the ladder over
      Firecrawl's markdown.
      **Dispatch is by NAME, not through a table.** The first version held a
      `dict[Rung, Callable]` built at import time, which captures the original
      functions — so `monkeypatch.setattr(fetcher, "_escalate_paid", fake)` kept
      calling the real one and two existing tests went red. A seam that works and
      cannot be tested is the failure mode this change exists to remove, so the
      dict is gone.
- [x] 3.3 **Unexpressible, and witnessed both ways.** Structurally:
      `test_escalation_cannot_be_separated_from_comprehension` asserts nothing
      dispatches a rung except `escalate`, that `escalate` always calls
      `_comprehend`, that `_comprehend` runs all three steps, and that nothing
      re-gates outside it. It REPLACES the weaker guard written in §1.4 — which
      could only ask "did each of four call sites remember one of three
      downstream steps", and they had not.
      Behaviourally: `tests/capabilities/tier_pipeline/test_post_gate_archive_comprehension.py`
      drives a real archive outcome through the seam and asserts the four
      consumers `eval/findings_2026-07-28.md` named are fed —
      `content_candidates` past one item, `record_set`, `record_count == 3` — plus
      the planner route (`_dispatch_action(post_gate=True)`), because asserting
      only on `escalate` would leave the path that HAD the bug untested. A fifth
      test is the anti-vacuity half: a FAILED dispatch must install and
      comprehend nothing, otherwise all four would pass on a context handed
      nothing.
      Three reversion probes, all observed failing: archive skipping
      comprehension (the old behaviour), `_comprehend` dropping sufficiency (H1's
      old shape), and a caller dispatching a rung directly.
- [x] 3.4 **Deleted — and it could not be deleted without making the assessment
      symmetric.** `_phase_listing_completeness` could only ever SET the partial
      signal; the CLEAR lived hand-written in `_phase_listing_render`, which is
      the tell the task named. Now that the loop head re-runs sufficiency after
      every escalation, the second pass is the one that matters, and a function
      that cannot retract would report a truncation the scroll had already
      resolved. The clear is now the `else` of the same branch.
      One improvement falls out: the deleted block re-assessed against the OLD
      `fc.items_total`, while the loop head reads the re-rendered page's own
      oracle.
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
