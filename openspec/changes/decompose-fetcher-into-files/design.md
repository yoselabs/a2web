## Context

`fetcher.py` at 2771 lines, having grown monotonically *through* its own v0.23
structural refactor. Line budgets below are from the 2026-07-31 AST census; the
tree is the applied form of the criterion.

The reason to state a criterion rather than a target: a line limit produces
`fetcher_a.py` and `fetcher_b.py`. The census showed the file's phases carry 5,
6, and 3 jobs respectively — the problem is purposes per file, and the tree falls
out of counting them.

## Goals / Non-Goals

**Goals**

- One file, one purpose.
- The retrieval→comprehension→sufficiency loop is a loop in the code.
- A stage cannot be skipped, because nothing calls it directly.
- The sufficiency question has a name.

**Non-Goals**

- Behaviour change, except the ladder skip that becomes unexpressible.
- Slicing `FetchContext` (phase two, blocked).
- The response contract (a different change).
- A stage framework (rejected below).

## Decisions

### D1 — The criterion

**One file, one purpose.** Exactly two exceptions: an **aggregation point** (a
composition root or entrypoint whose purpose IS to assemble) and a **utils leaf**
(shared mechanism with no domain decision in it).

Everything in the tree below is justified by that criterion, not by line count.
Line counts are shown because they are evidence the criterion was applied
honestly, not because they are the target.

### D2 — The tree

```
src/a2web/fetcher/
├── __init__.py            fetch() — AGGREGATION                    ~60
├── pipeline.py            the ordered chain, nothing else          ~50
├── context.py             FetchContext                              281
├── telemetry.py           UTILS                                      58
│
├── retrieval/             "get bytes for this URL"
│   ├── cache.py           TTL policy, read, write                    41
│   ├── conditional.py     the 304 path                              ~35   ← out of tier_walk
│   ├── cookies.py         resolve + staleness                        90
│   ├── proxy_lease.py     lease/report protocol                     ~45   ← out of tier_walk
│   ├── tier_walk.py       the walk itself                          ~180
│   ├── install.py         TierInstall + the one chokepoint          ~80   NEW
│   └── escalate/
│       ├── archive.py · browser.py · paid.py                       ~75 ea
│       └── _tail.py       shared install + re-gate — UTILS LEAF     ~35
│
├── comprehension/         "what did we get"
│   ├── prerendered.py     the handler-payload path                  ~70   ← out of ladder
│   ├── json_synth.py      JSON body → content                       ~60   ← out of ladder
│   ├── ladder.py          trafilatura → escalation rungs           ~140
│   ├── gate.py            evaluate / regate                          132
│   └── menu.py            candidates → prompt + wire                 191
│
├── sufficiency/           "is this ALL of it?"     ← has no name today
│   └── completeness.py    assess · oracle · scroll decision          138
│
├── answer/                "what did the caller ask"
│   ├── digest.py          {{n}} build + rehydrate (ADR-0014)          52
│   ├── prompt_call.py     the LLM call + degrade                     ~90   ← out of extract
│   ├── obstacle.py        the re-render decision                     ~60   ← out of extract
│   └── links.py           records→NextLink, LLM validation            95
│
└── verdict/               "what do we tell the caller"
    ├── promotions.py      empty · small-page                         ~50
    └── terminal.py        classify + hints (actions/ owns the        ~45
                           pure half already)
```

26 files, largest 281, then 191.

### D3 — The load-bearing part is the loop, not the tree

This is the decision that matters. The tree without it is cosmetics.

`retrieval → comprehension → sufficiency` **is a loop**, and the code does not
model it as one. Today escalation hand-calls comprehension from inside retrieval,
which is why:

- H1 exists at all — escalators re-enter at *comprehension* and skip sufficiency
  (`_run_extraction_escalation` 4 call sites vs `_phase_listing_completeness` 2)
- `_phase_listing_render:2716-2722` re-implements assess-and-set inline, because
  there is no loop head to return to
- `_phase_extract_answer` is re-entrant 3× and not idempotent — *answer* is being
  used as the loop body
- the single paid budget is resolved by call order across four competitors

**Have escalation return a retry signal instead of calling forward.** One path
from retrieval through comprehension to sufficiency; a stage cannot be skipped
because nothing calls it directly.

It also dissolves the `retrieval → comprehension` import cycle that blocks a
naive file split (anti-seam A2 in the scan). **The cycle WAS the loop, un-named**
— which is the strongest evidence available that this is the right seam: the
thing that made the split look impossible is the thing the split needs to name.

### D4 — `install.py` is the second load-bearing piece

Six transport fields are each written by six functions across three groups.
`_install_rendered_fields` already unified the content half — after it caused a
live bug — and explicitly excluded the transport half at `:1279-1281`.

One `install(ctx, TierInstall)` is what lets `tier_walk` and `escalate` be
siblings rather than one 576-line file. Without it the two must share a module to
share the writes.

Note what this does *not* fix on its own: the five install sites currently run
four different sequences (see the proposal's table). The chokepoint unifies the
writes; the loop unifies the sequence. Both are needed — the 2026-07-28 fix
collapsed the writes on one path and the fifth copy of the sequence bug survived.

### D5 — Rejected: a Stage protocol with declared reads/writes

A `Stage` protocol carrying `READS`/`WRITES` field sets would make the five
prose-only ordering constraints (`:1955`, `:2315`, `:2337`, `:2344`) checkable at
build time, and would make H1 **unexpressible**.

Rejected as a framework where a criterion was asked for. It spends magic budget
the Constitution does not want spent, for a guarantee the loop restructure
already delivers structurally.

**The cost, stated rather than hidden:** the residual ordering hazards go back to
being conventions —

- the paid budget resolved by call order,
- `fc.record_count` never resetting (`:1725-1732`, no `else: None`),
- `_install_gate_archive` not setting `status_code`.

They become **one architecture test**, not a framework. Cheaper, and the project
already has that habit. **If that test proves hard to write, reopen this decision
rather than living with the convention.** That is the tripwire; do not quietly
skip the test instead.

### D6 — Sequencing, and why phase two is blocked

**Phase one — the tree + the loop.** `FetchContext` stays whole. Closes H1.

**Phase two — slice `context.py` per node.** Blocked on
`unify-the-response-contract`: 41 of `FetchContext`'s 69 fields are read
externally by `fetcher_response.py`, so the response contract must absorb those
reads before the context can be split along them. ~19 test modules also import
`FetchContext`.

Attempting both at once turns a decomposition into a rewrite.

### D7 — The ladder-skip fix rides the loop, deliberately

The archive-post-gate skip (`fetcher.py:1058`) is a live defect and could be a
one-line fix today. Do it as part of the loop anyway: a one-line fix is the
fourth time this bug has been fixed one line at a time, and the fifth copy is the
evidence that approach does not hold. Once escalation returns a signal, the skip
is not expressible.

This is the *one* behaviour change in phase one, and it is a consequence rather
than a co-scheduled task. Everything else is a move.

## Anti-seams — verified, do not cut these

- **`_phase_tier_loop` / `_dispatch_action`:** the `:1247` escalation-win check is
  correct **only because** `_install_won_tier` at `:1254` has not run yet.
- **`_phase_empty_promotion` / `_phase_complete_small_page_promotion` /
  `_apply_terminal`** are one mutually-exclusive chain expressed by early
  returns, with `small_page_promoted()` reading a field written 460 lines away.
  They go into `verdict/` together or not at all.
- **`_phase_extract`'s pre-rendered branch:** `:1299-1323` documents that it once
  returned *before* the ladder and starved four consumers for months. Splitting
  it into `prerendered.py` must preserve the **ladder call**, not just the
  branch.
- **`FetchContext`:** 69 fields, ~19 test modules import it. Phase two only.

## Risks / Trade-offs

- **A 2771-line move is reviewable only if it is a move.** Any behaviour change
  beyond D7 hides in the diff. Land the loop and the tree; land nothing else.
- **The escalation-returns-a-signal restructure is the risky part**, not the file
  split. It changes control flow on four paths, three of which are the ones that
  currently differ. Expect the tier-loop tests to be the ones that find problems.
- **The tree could be wrong at the leaves.** `escalate/_tail.py` is the one file
  placed by judgement rather than census — the shared ~35-line install-and-re-gate
  tail (`_escalate_browser:2136-2151` ≈ `_escalate_paid:2236-2253`). It qualifies
  as a utils leaf; confirm that reading before writing it.
- **26 files is a lot of import churn** for ~19 test modules. Phase one keeps
  `FetchContext` whole specifically to bound that.

## Open Questions

- Confirm `escalate/_tail.py` really is a utils leaf and not a third escalator's
  worth of policy. Read both tails side by side before creating the file.
- Does the retry signal carry *what* to retry (a stage marker) or just "retry"?
  A marker is more expressive and more rope. Leaning bare signal plus the
  existing context state.
- Diagnostics currently append only-on-success in `_dispatch_archive:899` and
  always in browser `:2105` / paid `:2210` / tier loop `:1183`. Unify to
  always-append as part of the loop, or leave as-is and record? Leaning unify —
  it is the same divergence class as the install sequence.

## Phase two: unblocked 2026-08-01

`unify-the-response-contract` §7 derived and froze the response builder's slice
of `FetchContext`: **42 of 72 fields**, listed in
`tests/architecture/test_response_context_slice.py`. That ledger is what phase
two needed — the set is now stated and cannot grow silently, so `context.py` can
be sliced per node against a known boundary instead of a hand re-derivation.

Two caveats for whoever picks it up:

- The ledger is a LEDGER, not a Protocol. Adding a read is expected; the guard
  just makes it visible. A real `Protocol` was deliberately deferred — declaring
  42 members with live annotations pulls every one of their types into
  `fetcher_response.py`'s namespace, which is worth doing when the slice has an
  actual consumer, not before.
- 42 of 72 is high. The response builder reads well over half the context, so
  "slice per node" will not be a clean partition — expect a shared core.
