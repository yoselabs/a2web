## Why

`fetcher.py` is **2771 lines** — 3× the next-largest file — with the most commits
(78, 2× the next) and 10.8% of all `src/` churn.

The decisive fact is not the size. It is that **v0.23's structural refactor
already reorganized its interior into named phases, and the growth curve did not
bend**:

```
2026-05-15   913        2026-07-01  1728
2026-06-01  1610        2026-07-15  2547   ← +819 in two weeks
2026-06-15  1711        2026-07-31  2771
```

Interior reorganization is not the fix. A second same-shaped refactor should be
expected to produce the same result.

**Three live defects are caused by the missing structure, not by any single bug:**

1. **The archive-post-gate path never runs the extraction ladder.**
   `fetcher.py:1058` installs content and transport and re-gates at `:1059`,
   skipping the ladder. `fetcher.py:1299-1333` documents the *identical* bug one
   level up — skipping the ladder "starved four consumers"
   (`content_candidates`, `other_pages`, `record_count`, `record_set`) — fixed on
   the tier-loop path on 2026-07-28. Same bug class, **fifth copy, still live**.
   Five install sites, four different sequences:

   | site | file:line | installs | re-runs ladder | re-gates |
   |---|---|---|---|---|
   | tier-loop win | `fetcher.py:1254` | transport | yes | later |
   | archive, pre-gate | `fetcher.py:1062` | transport | yes | later |
   | **archive, post-gate** | **`fetcher.py:1058`** | content+transport | **NEVER** | `:1059` |
   | browser | `fetcher.py:2136-2151` | content+transport | conditional | `:2151` |
   | paid | `fetcher.py:2236-2253` | content+transport | conditional | `:2253` |

   `_install_rendered_fields`'s own docstring (`:1262-1282`) is a confession:
   *"THE ONLY PLACE THIS COPY IS WRITTEN. There were FOUR, and they disagreed."*
   The field-copy was collapsed; **the sequence around it was not.**

2. **Escalators re-enter at comprehension and skip sufficiency entirely** —
   `_run_extraction_escalation` has 4 call sites,
   `_phase_listing_completeness` 2. That is the H1 hypothesis, and it exists
   because escalation calls *forward* instead of returning to a loop head.

3. **`_phase_listing_render:2716-2722` re-implements assess-and-set inline**,
   because there is no loop head to return to.

Underneath: `_phase_extract_answer` is re-entrant 3× and not idempotent —
*answer* is being used as the loop body. The single paid budget is resolved by
call order across four competitors. Diagnostics are appended only-on-success in
`_dispatch_archive:899` and always in browser `:2105` / paid `:2210` / tier loop
`:1183`.

Four phases fail the one-file-one-purpose criterion outright: `_phase_tier_loop`
carries 5 jobs, `_phase_extract_answer` 6, `_phase_extract` 3, and the three
escalators share a duplicated tail.

**And the sufficiency question — "is this ALL of it?" — has no name anywhere in
the codebase.** It is the question ADR-0015 exists to answer.

## What Changes

- **`fetcher.py` becomes `fetcher/`** — 26 files, largest 281 (`context.py`),
  then 191, nothing over 300, grouped by the question each answers:
  `retrieval/` (get bytes) · `comprehension/` (what did we get) ·
  `sufficiency/` (is this all of it) · `answer/` (what did the caller ask) ·
  `verdict/` (what do we tell the caller).

- **`retrieval → comprehension → sufficiency` becomes an explicit loop.** Today
  escalation hand-calls comprehension from inside retrieval. **Have escalation
  return a retry signal instead of calling forward.** Then there is exactly one
  path through the stages and a stage cannot be skipped, because nothing calls it
  directly. This closes H1 *structurally* rather than by inspection, and it
  dissolves the `retrieval → comprehension` import cycle that blocks a naive file
  split — **the cycle WAS the loop, un-named.**

- **One `install(ctx, TierInstall)` chokepoint.** Six transport fields (`body`,
  `content_type`, `final_url`, `tier_used`, `pre_rendered_payload`,
  `status_code`) are each written by six functions across three groups.
  `_install_rendered_fields` already unified the *content* half after it caused a
  live bug and explicitly excluded the transport half (`:1279-1281`). One install
  type is what lets `tier_walk` and `escalate` be siblings rather than one
  576-line file.

- **`sufficiency/` gets a directory**, which is what gives the question a
  structural home.

- **The archive-post-gate ladder skip is fixed** as part of the loop, not
  separately — it is unexpressible once escalation returns a signal.

## Capabilities

### New Capabilities

None. This is the same pipeline with the same behaviour, expressed so that the
skips are impossible.

### Modified Capabilities

- `tier-pipeline`: escalation SHALL return a retry signal rather than invoking
  downstream stages; every retrieval SHALL pass through comprehension and
  sufficiency by the same path.
- `listing-completeness`: the sufficiency assessment SHALL run on every path that
  produced new content, including escalated ones.

## Impact

- `src/a2web/fetcher.py` → `src/a2web/fetcher/` (26 files)
- `src/a2web/fetcher_response.py` — phase two only, and blocked on
  `unify-the-response-contract`
- ~19 test modules import `FetchContext` directly
- CLAUDE.md — the pipeline description is wrong today anyway (`_run_pipeline` is
  documented as "a 12-line coordinator calling six named phases"; it is 47 lines
  calling twelve, and `_phase_cache_write` is not terminal)
- No dependency changes. No wire changes.

## Sequencing

**Phase one — the tree + the loop.** Does NOT need `context.py` sliced;
`FetchContext` stays whole. Closes H1 structurally. Fixes the archive-post-gate
skip as a consequence.

**Phase two — slice `context.py` per node. Blocked on
`unify-the-response-contract`**: 41 of its 69 fields are read externally by
`fetcher_response.py`, so the response contract must absorb those reads first.
Attempting both phases at once turns a decomposition into a rewrite.

## Out of Scope

- **A `Stage` protocol with declared `READS`/`WRITES` field sets.** Considered
  and rejected. It would make the five prose-only ordering constraints (`:1955`,
  `:2315`, `:2337`, `:2344`) checkable at build time and would make H1
  *unexpressible* — but it is a framework where a criterion was asked for, and it
  spends magic budget the Constitution does not want spent for a guarantee the
  loop restructure already delivers structurally.

  **What that costs, stated plainly:** the residual ordering hazards — the paid
  budget resolved by call order, `fc.record_count` never resetting (`:1725-1732`,
  no `else: None`), `_install_gate_archive` not setting `status_code` — go back
  to being conventions. They become **one architecture test**, not a framework.
  If that test proves hard to write, reopen this decision rather than living with
  the convention.

- The `fetcher_response.py` / `models.py` split. That is
  `unify-the-response-contract`.
- Any behaviour change beyond the ladder-skip fix. This is a move, and it must
  not simultaneously be a bug fix — that is exactly what v0.23 demonstrated.
