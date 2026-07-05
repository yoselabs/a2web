## Why

The extractor already knows when retrieval failed — it just can't act on it. The
LLM emits `obstacle ∈ {empty, blocked}` when the answer isn't in the content it
was given (a fat SPA shell that passed the length floor, a soft block that
slipped the gate). Today (v0.29.0) that signal only *downgrades confidence* and
sets `retrieval_incomplete` — it declares defeat. It cannot trigger a re-fetch,
because `obstacle` is born in `_phase_extract_answer`, which runs *after* the
gate/escalate phase where all rendering happens.

This is the deepest of the retrieval-miss tracks, and it closes two at once:

1. **The confabulation loophole.** A fat SPA shell (>500 chars) passes the length
   floor and the block regexes; only the LLM notices "the answer isn't here." A
   render (Zyte `browserHtml`) would get the real content — but nothing acts on
   the obstacle.
2. **Generic SPA-search-host coverage (Track 4).** The reason we can't hand-code
   a generic SPA-shell detector is that the LLM's `obstacle` signal *is* that
   detector. Wiring obstacle→render covers **any** host generically — no per-host
   escalate_to_render rule. Track 4 falls out for free.

## What Changes

- **New pipeline phase `_phase_obstacle_render`**, after `_phase_extract_answer`.
  When the extractor flagged `obstacle ∈ {empty, blocked}` (`_INCOMPLETE_OBSTACLES`
  — reused so the trigger stays in lockstep with the completeness logic), it
  dispatches a paid render of the original URL, re-extracts content, and re-runs
  the answer extraction over the real content.
- **Strict cost guard.** The render fires only when ALL hold: the `ask` path is
  active (obstacle exists only there); `obstacle ∈ {empty, blocked}`; no paid
  render was already spent (`fc.paid_dispatches < 1` — so a handler/gate render
  earlier suppresses this); and a paid tier is keyed (else `_escalate_paid` is a
  no-op). Bounded to **one** extra render + **one** extra LLM call per fetch.
  `paywalled`/`error` obstacles do NOT trigger a render (a render won't clear a
  paywall; archive owns that path).
- **Never-silently-miss preserved.** If no paid tier is keyed, or the render
  produces nothing new, or the re-extraction still reports `obstacle ∈ {empty,
  blocked}`, the v0.29.0 `retrieval_incomplete` + critical hint stands — the miss
  is still loud.

## Capabilities

### New Capabilities
<!-- none — extends existing capabilities -->

### Modified Capabilities
- `tier-pipeline`: a new `_phase_obstacle_render` phase runs after answer
  extraction; the extractor's `obstacle` signal can drive a paid render + a
  bounded pipeline-tail re-run (extract → answer → cache).
- `retrieval-completeness`: before an `ask` declares `retrieval_incomplete` on an
  `empty`/`blocked` obstacle, the orchestrator SHALL attempt one paid render; the
  incomplete signal survives only if the render can't be done or doesn't help.
- `paid-fetch-tiers`: the paid last-resort tier gains a second trigger — an
  extractor `obstacle ∈ {empty, blocked}` — in addition to gate walls and handler
  `escalate_to_render`. The one-dispatch-per-fetch cap is shared across all
  triggers.

## Impact

- **Code**: `src/a2web/fetcher.py` (`_phase_obstacle_render` + `_run_pipeline`
  wiring; reuses `_escalate_paid`, `_phase_extract`, `_phase_extract_answer`,
  `_phase_cache_write`); import `_INCOMPLETE_OBSTACLES` from `fetcher_response`.
- **APIs / envelope**: none. `obstacle` / `retrieval_incomplete` / `confidence`
  fields already exist; this changes *when* they land (post-render), not their
  shape. No new tool params.
- **Cost**: +1 render + +1 LLM call on the `ask` path only, only on
  `empty`/`blocked` obstacles, only when paid-keyed, capped at 1 — the explicit,
  accepted cost.
- **Dependencies**: none.
- **Out of scope** (stays in `BACKLOG.md`): requested-vs-actual URL transparency
  (Track 1). `fetch_raw`-over-SPA has no LLM/obstacle, so it is not covered here
  (the confabulation risk lives on the `ask` path).
