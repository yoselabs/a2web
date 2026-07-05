## Context

The cascade is a linear phase sequence (`_run_pipeline`):

```
cache_check → tier_loop → extract → gate_and_escalate → cache_write
            → extract_answer → cookies_staleness → build_response
```

All rendering/escalation lives in `gate_and_escalate` (browser, archive, paid).
The LLM answer + its `obstacle` signal are produced later, in `extract_answer`
(`fc.routing.obstacle`). So the one component that can authoritatively say "the
answer isn't in this content" speaks *after* the last chance to fetch more. The
v0.29.0 confabulation guard consumes `obstacle` only in the ask projection
(`build_ask_response`): it caps confidence and, for `obstacle ∈ {empty,
blocked}` (`_INCOMPLETE_OBSTACLES`), sets `retrieval_incomplete` + a critical
hint. That's the whole loop today — detect, then give up.

The render machinery already exists and is battle-tested: `_escalate_paid(fc,
state)` dispatches the paid tier (`_PAID_TIER_ORDER`) onto `fc.final_url`,
installs `fc.pre_rendered_payload` on success, records diagnostics, fail-louds on
`paid_auth_error`, and bumps `fc.paid_dispatches` unconditionally at entry (the
cap). It is already invoked two ways: a gate wall (`paid_last_resort` planner
rule) and a handler `escalate_to_render`. This change adds a third trigger.

## Goals / Non-Goals

**Goals:**
- Let `obstacle ∈ {empty, blocked}` drive exactly one paid render + a bounded
  re-extraction, so a confabulated shell becomes real content.
- Cover generic SPA-search hosts (Track 4) via the LLM signal — no per-host rule.
- Preserve never-silently-miss: an unresolved obstacle still yields
  `retrieval_incomplete` + the critical hint.
- Zero envelope change; strict, bounded cost.

**Non-Goals:**
- Rendering on `paywalled` / `error` (a render won't clear a paywall; archive
  owns paywalls). Only `_INCOMPLETE_OBSTACLES`.
- Covering `fetch_raw` (no LLM → no obstacle; and no LLM asserting a wrong answer,
  so the confabulation risk isn't there).
- A general multi-pass extraction loop. One render, one re-extract, hard stop.

## Decisions

### D1 — New phase `_phase_obstacle_render` after `_phase_extract_answer`

```
… extract_answer → OBSTACLE_RENDER → cache_write → cookies_staleness → build_response
```

`cache_write` moves to *after* the render phase so the cache stores the final
(possibly re-rendered) body exactly once, and a confabulated shell never lands in
the cache. `extract_answer` does not mutate the cacheable body/`content_md` on the
no-obstacle path, so relocating `cache_write` past it is behavior-preserving for
the common case (verified: `extract_answer` writes `extracted_answer` / `routing`
/ `next_links_llm`, never `body` / `content_md`).

*Alternative considered:* keep `cache_write` where it is and re-run it inside the
render phase. Rejected — it briefly caches the shell and double-writes; moving the
single `cache_write` to the tail is cleaner and closes the shell-in-cache window.

### D2 — Trigger predicate (the cost guard)

Fire the render iff ALL hold:
- `fc.ask is not None` (obstacle exists only on the ask path)
- `fc.routing is not None and fc.routing.obstacle in _INCOMPLETE_OBSTACLES`
  (import the frozenset from `fetcher_response` — single source of truth, kept in
  lockstep with the incomplete/confidence logic)
- `fc.paid_dispatches < 1` (no paid render already spent — a handler/gate render
  earlier means we already have the best content; don't pay twice)
- a paid tier is registered (implicit: `_escalate_paid` no-ops and just bumps the
  counter when none is keyed → the guard below sees no new content and bails)

`fc.resolved_verdict()` is `ok` here (extraction only ran on `ok`), so no extra
verdict guard is needed.

### D3 — Action: render → re-extract → re-answer, with a fallback snapshot

```python
async def _phase_obstacle_render(fc, *, state):
    if not _obstacle_wants_render(fc):        # D2 predicate
        return
    prev_md = fc.content_md
    await _escalate_paid(fc, state=state)     # installs rendered content_md,
                                              # runs the extraction-escalation
                                              # ladder, and re-gates (existing)
    if fc.content_md == prev_md:              # unavailable / failed / identical
        return                                # v0.29.0 retrieval_incomplete stands
    await _phase_extract_answer(fc, state=state)  # fresh answer + fresh obstacle
```

- `_escalate_paid` already does the heavy lifting on success: it sets
  `fc.content_md` / `fc.body` / `fc.pre_rendered_payload`, runs
  `_run_extraction_escalation` on the rendered HTML, and calls
  `_regate_after_escalation`. So the phase does NOT call `_phase_extract` — only
  the answer needs re-running.
- The `content_md == prev_md` guard covers every no-progress path (no paid tier
  keyed → `_escalate_paid` no-ops; timeout/connection failure; a `paid_auth_error`
  hard-stop before install). On `paid_auth_error` the authoritative verdict wins
  `resolve_verdict`, so `build_response` reports it loud and the guard skips the
  re-answer.
- `_escalate_paid` bumps `paid_dispatches` on entry, so even a still-empty
  re-extraction cannot re-enter — the cap guarantees termination (the phase runs
  once in the linear pipeline anyway; the bump is belt-and-suspenders).
- The re-gate inside `_escalate_paid` is authoritative content handling; the
  *fresh* `obstacle` from the re-extraction is the completeness check. If it is
  still `empty`/`blocked`, `retrieval_incomplete` holds (loud miss).

*Alternative considered:* re-run `_phase_gate_and_escalate` after the render.
Rejected — it would re-arm browser/archive escalation and risk a second paid
dispatch; the fresh obstacle already provides the completeness gate.

### D4 — `paid_auth_error` still fails loud

`_escalate_paid`'s existing fail-loud contract is unchanged: a bad paid key
records an authoritative `paid_auth_error` (wins the verdict) and stops. In the
obstacle-render path that means `fc.resolved_verdict()` flips to `paid_auth_error`
→ `build_response` reports the misconfiguration loudly. The re-extract guard
(`content_md == prev_md`) skips re-answering on that path.

## Risks / Trade-offs

- **[Double LLM spend on a false-positive obstacle]** (LLM says `empty` when the
  answer was actually present) → mitigated: capped at 1, ask-path only, and the
  re-extract only runs if the render produced *different* content. Worst case is
  one wasted render+call on a page the model mis-judged.
- **[A genuinely empty page renders empty too]** → the fresh obstacle stays
  `empty`, `retrieval_incomplete` holds, no loop (cap). Correct outcome.
- **[Relocating `cache_write`]** → guarded by the invariant that `extract_answer`
  doesn't touch the cacheable body; a test asserts the no-obstacle path caches
  identically to today.
- **[Latency]** → an extra render (~seconds) + LLM call on the ask path when an
  obstacle fires. Accepted: it converts a wrong/empty answer into a real one; the
  guard keeps it off the ~95% healthy path.

## Migration Plan

Additive phase on the ask path; no envelope change, no config, no data migration.
Rollback = revert (obstacles return to downgrade-only). Ships in a version bump;
`make install-global` propagates.

## Open Questions

- **Re-render content that is ALSO thin** — after the paid render, should the
  re-extraction feed the gate's length floor? Current call: no (render is
  authoritative; the fresh obstacle is the check). Revisit if a real case shows a
  thin *rendered* page confabulating.
- **`error` obstacle** — excluded for now (a render rarely clears a server error).
  Revisit if telemetry shows `error` shells that a render would fix.
