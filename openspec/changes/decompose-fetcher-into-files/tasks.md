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
- [x] 3.5 **One caller now — `_phase_answer` — and the re-entry is visible
      instead of eliminated.** The three entries were the phase sequence plus
      each render phase deciding for itself whether the answer needed
      recomputing. The re-entries are CORRECT: an obstacle render exists
      precisely because the answer said the content was not here, and re-running
      it over fresh content is the point. What was wrong is that they were
      invisible — "how many LLM calls does this fetch make" was answerable only
      by reading three functions.
      So both render phases now return "content changed" and re-answering is the
      head's job. The sequence is byte-identical (answer → obstacle →
      answer-if-changed → listing → answer-if-changed), hoisted, not reordered.
      **Deliberately NOT a `while` loop**: that would re-run the obstacle render
      after a listing render changed the content, which is a second render
      nobody asked for.
      **Two real defects fell out of making the re-entry visible**, both filed
      rather than fixed (behaviour change, and this is a move):
      `fc.extraction_meta` is OVERWRITTEN on the second call, so a fetch that
      made two billed LLM calls reports one call's tokens and cost — biased
      toward the expensive fetches, since a render is what triggers the second
      call; and `fc.next_links_llm` is assigned only inside
      `if result.next_links:`, so a second extraction returning none leaves the
      FIRST call's links in place, validated against markdown that has since
      been replaced. That is an ADR-0014 violation reached by staleness rather
      than hallucination, on the exact path a guard exists to protect.
      `test_the_answer_stage_has_exactly_one_caller` keeps the re-entry pinned
      to one site while they are open.
      **The §1.4 guard earned itself here**: it was written against the direct
      `_phase_extract_answer` call in `_run_phases` and went red the moment the
      call became indirect. The constraint had not changed, so the guard
      followed the indirection rather than being deleted — which is the whole
      reason it was written before any cutting.
- [x] 3.6 **Confirmed after §4, and the prediction held: zero cycles.** A DFS
      over every relative import in the tree finds no cycle at file granularity —
      the first measurement, taken before the loop was modelled, found one
      (`install` ↔ `escalate.archive`), which is what §3.6 predicted the loop
      WAS. At GROUP granularity `retrieval` and `comprehension` still name each
      other, and that is not a residual cycle: `comprehension/extract.py` imports
      `retrieval/install.py`, a leaf that imports nothing back. The direction that
      mattered — comprehension reaching back INTO escalation — is gone, and
      `escalate → _comprehend` is one-way.
- [x] 3.7 **Partly. The cap is now single-sited and the four claimants share one
      predicate; the PRECEDENCE is stated rather than changed — and saying so is
      the honest half.**
      What was there: eleven `< 1` / `< 2` literals across `playbook.py` and
      `fetcher.py`, in two modules that cannot see each other's copies. That is
      the `NEXT_LINKS_CAP` shape exactly — one stated invariant with six
      implementations, one of which shipped five times the cap while a probe
      recorded the violation as healthy. Now `URL_REWRITE_CAP`,
      `ARCHIVE_DISPATCH_CAP`, `BROWSER_DISPATCH_CAP` and `PAID_DISPATCH_CAP` are
      declared once in `actions/playbook.py` (the pure module both sides may
      import), and the four paid claimants call `paid_budget_available(fc)`.
      What was NOT done, deliberately: the winner is still decided by call
      order. Four independent tests whose outcome fell out of which phase ran
      first is now one function whose docstring NAMES the four claimants in
      precedence order — forced site render, planner last-resort, obstacle
      render, listing scroll. Reading the code told you the cap four times and
      the order zero times; it now tells you the order once. Changing who wins
      (an obstacle render arguably beats a listing scroll on value per dollar)
      is a behaviour change and belongs to its own change.

## 4. Phase one — the tree — DONE 2026-08-02

Cut by line range rather than by re-authoring, so every comment travelled with
the node it explains. 3018 lines → 24 modules under five groups named for the
question each answers.

- [x] 4.1 Done. `FetchContext` stays whole in `context.py` — phase two.
- [x] 4.2 **Five of seven.** `cache`, `cookies`, `tier_walk`, `install`,
      `escalate/` (five modules: `archive`, `browser`, `paid`, `seam`, `loop`).
      `conditional` and `proxy_lease` were NOT split out of `tier_walk`, and the
      honest reason is that neither is a unit: the 304 path is four lines inside
      the tier loop's body that read a cache row the same function already holds,
      and the proxy lease is a `with` block wrapping the dispatch. Extracting
      either means inventing a parameter object to carry the loop state across
      the seam — the god-setter shape §2.1 refused. Recorded as a deliberate
      shortfall, not an oversight; `tier_walk.py` is the largest non-context
      module at 348 lines because of it.
- [x] 4.3 **Three of five, same reason.** `ladder`, `gate`, `menu`, plus
      `extract`. `prerendered` and `json_synth` stayed inside the ladder: they
      are the ladder's two rungs and each is a single function that writes the
      candidate list the ladder owns.
- [x] 4.4 Done — `sufficiency/completeness.py`. The question ADR-0015 exists to
      answer now has a directory with its name on it.
- [x] 4.5 Done — `answer/{links,digest,prompt_call,obstacle}.py`.
- [x] 4.6 Done — `verdict/{promotions,terminal}.py`, in one directory. They are
      mutually exclusive by early return, so the group is the unit.
- [x] 4.7 **Not met, and the estimate was wrong in a way worth stating.** Three
      files exceed 300 lines: `__init__.py` at 499, `context.py` at 425, and
      `tier_walk.py` at 348. Two of the three are explained above (context is
      phase two; tier_walk is 4.2's shortfall). The third is the compat surface:
      `__init__.py` re-exports 98 names so `from a2web.fetcher import X` keeps
      working, and 98 of its 499 lines are an `__all__` declaring that surface
      rather than logic. The design's "281 lines" for `context.py` was measured
      against the 2771-line file; it is 425 today for the same reason the whole
      file was 3018 — it grew in the interval.
      Median module is 136 lines. `fetch` itself, the entry point, is 30.

## 5. Phase one — the residual-ordering guard — DONE 2026-08-02

- [x] 5.1 `tests/architecture/test_fetcher_residual_ordering.py`, registered in
      `docs/architecture/README.md`. Three tests, one per hazard.
      **The paid budget** — no function reads `fc.paid_dispatches` outside the
      predicate, and every claimant the precedence docstring names must exist AND
      still ask. The table records HOW each asks, because they do not all ask the
      same way: `_decide_paid_last_resort` lives in `actions/playbook.py`, the
      pure module both sides import, so it can see `PAID_DISPATCH_CAP` but not
      the fetcher-side predicate. Writing the guard is what surfaced that — the
      first version assumed one spelling and named `_dispatch_action`, which
      dispatches the action the planner already decided.
      **Re-comprehension staleness** — a ledger of every field the second
      comprehension pass can leave holding the first pass's value. The
      discrimination is "written, and never re-derived": a field assigned
      unconditionally, or assigned a clearing constant on some path, is
      recomputed each pass; anything else is carried. Four fields, two intended
      (`next_links_handler`, `record_set` — producer-claim precedence) and two
      **not**, which is a finding the task did not predict: `record_count` (the
      one §5.1 named) plus **`regex_oracle_total`**, which is worse in a small
      way — `_apply_llm_listing_oracle` stands down on exactly that field, so a
      stale total from a replaced body silently disables the language-agnostic
      LLM superset. Filed in `BACKLOG.md`; both are behaviour changes.
      **The archive install pair** — subsumed by §2's chokepoint, asserted by
      name so §5.1's third hazard is closed rather than assumed.
- [x] 5.2 All three reversion-verified: swapping `paid_budget_available(fc)` back
      to a `< 1` literal in `_obstacle_wants_render`; deleting §3.4's symmetric
      clear (`items_loaded`/`items_total` appear as undeclared sticky fields —
      the guard catches the exact regression §3.4 fixed); hand-writing
      `_install_gate_archive`'s fields instead of calling `install`. Each observed
      failing, each reverted. Both walks also carry their own floors: the field
      walk asserts it found writes AND found re-derived writes, because if the
      renewal discrimination matched nothing every field would read as sticky and
      the ledger would be measuring the wrong thing.
- [x] 5.3 **Tripwire not tripped — the Stage-protocol decision stands.** The test
      was not hard to write; it took one file and three walks. Stated plainly
      because the tripwire only means something if it could have fired: what made
      it easy is that §2 and §3 had already collapsed two of the three hazards
      into chokepoints, so the guard mostly had to assert that the chokepoints are
      the only path. A Stage protocol would have bought the third (field
      staleness) structurally, by handing each pass a fresh output object; the
      substitute here is that the set is closed and named.

## 6. Phase one — close out

- [x] 6.1 Green: **1520 passed, 2 deselected, 1 xfailed, 91.84% coverage, 152
      tach tests.** The only behaviour change is D7's ladder skip.
      Landing it cost seven full-suite rounds and ~30 tool calls against a
      ~3-minute task, which is itself a finding: the breakage was greppable
      before the first run. Two classes, both about test SEAMS rather than
      behaviour. **Patch targets on the package instead of the owning module** —
      a re-export is a second binding, so `monkeypatch.setattr(fetcher, name,
      fake)` leaves the definition and every caller's view untouched. And
      **`monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)`**, of which
      most instances were patching a value back to itself; the split only made
      two of them visibly inert, and those two were asserting *the browser is NOT
      dispatched* and had been passing for the wrong reason the whole time.
- [x] 6.2 **Run 2026-08-02, operator-approved.** `eval/runs/2026-08-02_133205` —
      132 cells, $10.12, 926s. Findings: `eval/findings_2026-08-02.md`.

      **This change did not move behaviour**, which is what a pure restructuring
      owed: contract conformance 44/44 on both a2web systems, and no URL class
      shows the collapse a mis-wired escalation seam would produce.

      The run earned its cost on two OTHER things, neither of which this change
      caused and both of which it surfaced:

      - the first attempt **died at cell 24 of 132**, ~$3.18 spent, no report —
        a judge policy callable raising past the runner's per-cell isolation
        (fixed `dcdfd5a`; analysis deferred to `BACKLOG.md`). The re-run is the
        foreign witness for that fix: the same wobble recurred four times and
        each cost one cell, not the matrix.
      - the new `walled-listing-recovered-via-archive` corpus case caught a live
        ADR-0009 hole — a tier-declared paywall matched no planner rule at all
        and returned `Continue` with no rung attempted (fixed `82aa421`).

      The headline product finding is unrelated to this change and is recorded
      for whoever picks it up: **`a2web_detail`'s clarity is 1.46, below the
      WebFetch baseline's 3.44**, while `a2web_extract` matches its answer
      quality at one sixth the tokens. Do not read the 2.98-vs-2.95 quality gap
      as real — the per-system `n` differs (41/43/44) and three of four unscored
      cells landed on one system.
- [x] 6.3 `walled-listing-recovered-via-archive` — a walled news ARCHIVE INDEX,
      recovered from Wayback. Both structural facts verified before writing the
      entry rather than assumed: the live URL 401s to server-side clients (which
      is what forces the planner's `RetryViaArchive`), and the CDX API returns
      200-status snapshots back to 2007 (which is what makes recovery possible).
      A listing is the right shape for this cell because the starved consumers
      are all index consumers — an uncomprehended snapshot cannot emit
      `other_pages` at all, so the failure is visible in the wire rather than
      only in the prose.
- [x] 6.4 Done during §4 — CLAUDE.md's `src/a2web/fetcher.py` line is now a
      description of `src/a2web/fetcher/` naming the two load-bearing seams
      (`install`, `escalate`) and the module-not-name rule. The "12-line
      coordinator" sentence it was supposed to correct is gone with it.
- [x] 6.5 Baseline recorded, 2026-08-02, immediately post-split:

      | module | lines |
      |---|---|
      | `fetcher/__init__.py` | 499 |
      | `fetcher/context.py` | 425 |
      | `fetcher/retrieval/tier_walk.py` | 348 |
      | `fetcher/comprehension/ladder.py` | 237 |
      | `fetcher/answer/prompt_call.py` | 198 |
      | *(19 more)* | ≤ 168 |
      | **total** | **3893** |

      Median 136. The pre-split file was 3018 lines in one module; the tree is
      3893 across 24, and the +875 is the split's own cost — per-module
      docstrings, the import headers each module needs, and the 98-name
      `__all__` compat surface in `__init__.py`.
      **What a future scan should ask is not "did the total grow".** The
      proposal's claim was that a single file grows monotonically because there
      is no cost to adding to it. The test of the seam is whether the growth is
      DISTRIBUTED: if `tier_walk.py` is 600 lines in six months while the median
      holds, the group boundaries worked and one module needs cutting; if every
      module grew evenly, they did not.

## 7. Phase two — BLOCKED on `unify-the-response-contract`

- [ ] 7.1 Confirm that change has landed and absorbed the 41 external
      `FetchContext` reads.
- [ ] 7.2 Slice `context.py` per node.
- [ ] 7.3 Update the ~19 test modules importing `FetchContext`.
- [ ] 7.4 Move the T1 entries to `BACKLOG-CLOSED.md`, including the two subsumed
      ones (*no "install a fetch result" type*, *five escalation decisions live
      outside the single policy function*) and *the sufficiency question has no
      name*.
