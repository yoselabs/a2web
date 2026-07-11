## Context

The escalation machinery in `fetcher.py` + `actions/playbook.py` is built on genuinely good patterns — an append-only observation log (`fc.observations`), a pure verdict projection (`resolve_verdict`), and a pure planner `decide_next(log, url, caps) -> Action` whose result is one of a reified 5-member `Action` union (`RewriteUrl | RetryViaArchive | EscalateBrowser | EscalatePaid | Continue`). The pattern's promise is *any decision is a pure function of the accumulated log, reachable from any state*.

That promise is broken by the **executor**, which is split across two phase-bound call sites:

- **In-band** — `_execute_tier_action()` (fetcher.py ~955), called inside the tier loop (~1145). Handles `RewriteUrl` (restart the tier walk), `RetryViaArchive`, and the ok-win install. Returns a `_Exec` enum (RESTART / STOP / CONTINUE).
- **Out-of-band** — the inline `while True` loop in `_phase_gate_and_escalate` (~1687). Handles `EscalateBrowser`, `RetryViaArchive`, `EscalatePaid` via `isinstance` dispatch.

Neither handles all five actions. `EscalateBrowser` is a silent no-op if produced in-band; `RewriteUrl` is "not used post-gate" (explicit comment, ~1705). The browser→archive→paid ladder lives *only* in the out-of-band loop, which only runs once the tier loop produced a 2xx body to extract-and-gate. On top of this, escalation policy is smeared across three more sites beyond the planner: the in-band `escalate_to_render` short-circuit (~1116, sets `render_requested` outside the planner), and two standalone phases `_phase_obstacle_render` / `_phase_listing_render` (~1984/1989) that re-implement dispatch-paid-render-then-regate wholly outside `decide_next`.

Net effect: a transport/status failure recorded in the log cannot reach the ladder, and adding any new escalation trigger means implicitly choosing one of four non-composing homes for it. The `cascade-decision-log` spec already *claims* the orchestrator "holds no escalation policy of its own" — this change makes that claim true.

## Goals / Non-Goals

**Goals:**
- One escalation driver that runs `decide_next` over the observation log until `Continue`, handling the full `Action` union, reachable from every pipeline position (not bound to the gate phase).
- All escalation *policy* single-sourced in `decide_next` / `_RULES` — fold the obstacle-render and listing-render decisions into planner rules; retire `escalate_to_render` as a policy site (handler still *signals*, planner *decides*).
- Model "restart the tier walk" as an explicit `Action`/driver outcome so the tier-loop restart and post-gate escalation are one mechanism.
- Preserve every observable invariant: verdict = pure log projection; browser cap 2, paid cap 1; block-pages-never-cached; render-before-cache-write ordering; ADR-0009 loud incompleteness.

**Non-Goals:**
- NOT widening which outcomes escalate. This refactor is output-preserving; it must not change which URLs succeed vs. fail today. Transport-failure rules are Step 2, a separate additive change that drops into this executor once it exists.
- NOT the shelf `http-fetch` DNS split (Step 0) nor the archive-staleness hint (Step 3).
- NOT touching the planner's *pattern* (rules-by-priority), the decision log, the tier Strategy/Registry, or the `Action` union's role — only how actions are *executed* and where the render/listing policy lives.

## Decisions

**D1 — One executor driver, phase-independent, over the log.** Introduce a single async `_drive_escalation(fc, state)` (name TBD) that loops: `action = decide_next(fc.observations, url=..., caps=_planner_caps(fc))`; dispatch by action type; stop on `Continue`. Both the tier loop and the gate phase call *this*, rather than each carrying its own dispatch. Rationale: the executor becomes a pure interpreter of the `Action` union, restoring the "any decision from any state" property. Alternative considered — keep two executors but teach each to handle all five actions: rejected, it doubles the dispatch surface and keeps the phase-coupling that hides the gap.

**D2 — "Restart the tier walk" becomes an explicit driver control outcome, not a hidden in-band-only path.** The driver's dispatch of `RewriteUrl` yields a typed "restart requested" signal the tier loop consumes; the post-gate caller simply never produces a state where a restart is planner-legal (or treats it as a no-op by construction, asserted in a test). Rationale: this is the *one* genuine reason the two executors diverged today (RewriteUrl restarts the loop; escalations don't) — making it a first-class outcome is what lets the two collapse into one without losing the restart semantics. Alternative — split `Action` into two unions (in-band vs. post-gate): rejected, it fractures the planner's single-source property and doubles rule bookkeeping.

**D3 — Finding 2 (single-sourcing the completeness-escalation policy) is DEFERRED to a follow-up change.** Reading the code revealed that `_phase_obstacle_render` and `_phase_listing_render` are not simple "return `EscalatePaid`" cases: the listing render needs `scroll=True` (which the `Action` union does not carry — it would need an `EscalatePaid(scroll=…)` variant), and both need a post-render re-extraction step (`_phase_extract_answer` again) that is phase-specific. Folding these naively would accrete scroll/re-extract special-casing *into* `_dispatch_action`, dirtying the very thing this change cleans. That is a distinct, coherent design concern — the `Action`-scroll vocabulary question deserves its own change — so it is split out as a follow-up (`single-source-escalation-policy`). This change is scoped to the executor unification (Finding 1), which is the load-bearing structural fix and unblocks Step 2 on its own. Alternative — do everything here: rejected, it enlarges an already-critical-path refactor and forces a rushed `Action`-vocabulary decision.

**D4 — (folded into D3.)** The `escalate_to_render` handler signal and its inline policy branch are UNCHANGED in this change; retiring that policy site is part of the deferred follow-up.

**D5 — Output-preservation is the acceptance bar.** The refactor lands only if the full existing suite (`cascade_decision_log`, `quality_gate`, `listing_completeness`, `retrieval_completeness`, tier-pipeline capabilities) stays green with no expectation edits that change observable output. New tests are additive: the single driver reaches every `Action` from a representative log; render/listing escalations still fire pre-cache. Rationale: a refactor that changes outputs is a different, riskier change — keep the widening (Step 2) cleanly separate so any output shift is attributable.

## Risks / Trade-offs

- **[Risk] The unified driver runs at the wrong pipeline position and a shell/partial body gets cached.** → Mitigation: an explicit test that an obstacle/listing escalation triggered by the driver completes before `_phase_cache_write`, plus the existing "block pages never enter the cache" capability test must stay green unmodified.
- **[Risk] Collapsing two executors silently drops the RewriteUrl restart semantics (tier walk never restarts).** → Mitigation: D2 makes restart a first-class outcome with a dedicated test (a `RewriteUrl` from the planner restarts the tier walk exactly as today; cap of 1 rewrite preserved).
- **[Risk] Folding phases into rules changes *ordering* of escalations relative to each other (e.g., obstacle-render now competes with browser escalation at a different priority).** → Mitigation: the new rules get explicit priorities placed to reproduce today's effective order; rule-identity + test-pair requirement (existing `cascade-decision-log` contract) forces a test per new rule.
- **[Trade-off] Larger blast radius than the cheap alternative** (just teaching the in-band executor to reach the ladder). → Accepted: the cheap patch would leave policy tri-partite and the pattern half-applied; this change is the one that makes the invariant structural. The cheap patch is explicitly the thing we're choosing *not* to do.
- **[Risk] Hidden readers of `render_requested` / the `_Exec` enum elsewhere.** → Mitigation: grep-audit all references before collapsing; the refactor is not done until those callers route through the driver.

## Migration Plan

Pure internal refactor — no data migration, no wire change, no feature flag. Land behind `make check` (lint + ty + full test + coverage ≥85%). Rollback is a plain revert; no external state depends on the executor's internal shape. Sequencing note: this is Step 1 of a four-step arc (Step 0 shelf DNS split; Step 2 transport-failure rules; Step 3 archive staleness) — it is the critical path that Step 2 depends on, and it ships independently of Steps 0/3.

## D6 — Honest two-region scope (resolved at implementation start, supersedes the "no phases" reading)

Reading the real code surfaced that the `RetryViaArchive` install genuinely differs by pipeline region: during the tier-walk it installs the body only (`_install_archive_payload`, no regate — the gate phase runs *later* and will gate it), while post-gate it installs and explicitly regates (`_install_gate_archive` + `_regate_after_escalation` — the gate already ran). This is not accidental coupling; it reflects the pipeline's legitimate shape: **walk tiers → gate → escalate**. Pushing to a literal "no phases, one flat loop" would require gating *every* tier attempt (not just the winner), which changes the observation-log contents and risks real output changes — violating D5 for no product gain (purity for purity's sake).

**Decision:** unify the *executor* (one `_dispatch_action` handling the full 5-member `Action` union, so the escalation ladder is reachable from any post-observation position — this is the structural fix for Finding 1 and what makes the transport-failure rules of Step 2 a drop-in), single-source the *policy* (fold obstacle/listing/`render_requested` decisions into planner rules — the fix for Finding 2), and represent the one genuine region divergence honestly as a `post_gate: bool` parameter on the dispatcher (selecting the archive install-variant + regate), rather than pretending it away. The spec's "reachable from every position where an observation was just appended" is fully met; "not bound to a single pipeline phase" is met for *policy* (all in the planner) and for the *executor mechanism* (one dispatcher), with the archive install-position being an explicit, documented parameter — NOT overclaimed as full phase-independence. The delta spec is tightened to match (see the `cascade-decision-log` delta's executor requirement).

Resolved Open Questions:
- Unified driver: a single `_dispatch_action(fc, action, *, state, post_gate) -> _Exec` shared by the tier-loop and the post-gate/post-extraction driver loop; `_run_pipeline` keeps its phase sequence but the escalation *dispatch* is one function.
- Restart modeling (D2): `_dispatch_action` returns `_Exec.RESTART` for `RewriteUrl`; the tier loop consumes it; post-gate the planner never returns `RewriteUrl` (asserted by test), so the same return is a harmless no-op there.
- Obstacle vs. listing rules: two distinct `PlannerRule`s (distinct trigger predicates and priorities), both returning `EscalatePaid`/the render action, sharing the paid cap — clearer than one over-parameterized rule.

## Open Questions

- (resolved — see D6)
