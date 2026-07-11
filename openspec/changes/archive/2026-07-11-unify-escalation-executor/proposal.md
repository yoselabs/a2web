## Why

a2web's escalation architecture uses mostly-right patterns — an event-sourced decision log with a pure verdict projection, a pure planner `decide_next(log) -> Action`, and reified Command-object actions — but the **executor half is fragmented and phase-coupled**, so the pattern's central promise ("any decision reachable from any accumulated state") is not delivered. `decide_next` is called from two different pipeline phases wired to two different executors, and *neither* handles the full `Action` union. The browser→archive→paid escalation ladder physically lives in only one of them (the post-gate phase), which only runs after the tier loop produced a 2xx body to gate. A transport/status failure (bare 403 / 5xx / timeout / connection-reset) is recorded in the decision log but can never reach the ladder — it falls off the pipeline into a terminal "couldn't fetch" without browser and paid ever being tried. That is a structural violation of the never-tolerate-an-unfetched-URL invariant (ADR-0009), waiting to be triggered.

## What Changes

- **Unify the two divergent executors into a single `_dispatch_action` function.** Today the in-band `_execute_tier_action` (tier-walk) and the inline post-gate `while` loop each handle a different subset of the 5-member `Action` union, and neither handles all five. This change routes both call sites through one executor that handles the full union — so no `Action` type is a silent no-op where the planner can legally return it.
- **Make the escalation ladder reachable from any post-observation position.** Because both the tier-walk and the post-gate loop now dispatch through the same executor, `EscalateBrowser` → archive → `EscalatePaid` is no longer physically trapped in the post-gate phase — it is reachable from the tier-walk too. This is the structural fix that lets the Step 2 transport-failure rules drop in without new wiring.
- **Model "restart the tier walk" as a first-class executor outcome**, not an in-band special case. `RewriteUrl` restarting the tier loop is why the in-band executor existed separately; the unified executor represents this as an explicit `_Exec.RESTART` control outcome the tier loop consumes, so it is one mechanism, not two.
- **Represent the one genuine pipeline-region divergence honestly** as a `post_gate` parameter on the executor (design D6): `RetryViaArchive` installs the body only during the tier-walk (the gate runs later) but installs extracted fields and regates post-gate. This reflects the pipeline's real shape rather than pretending it away.
- This is a **behavior-preserving refactor at the observable-output level**: it does not change which URLs succeed vs. fail today. It makes the "escalation ladder reachable from anywhere" property *structural* rather than an accident of which phase a decision happens in.

Not in scope (separate changes, by design):
- **Finding 2 — single-sourcing the completeness escalation policy** (folding `_phase_obstacle_render`, `_phase_listing_render`, and the handler `escalate_to_render` ladder into planner rules) is a **follow-up change**: it requires designing an `EscalatePaid(scroll=…)` Action variant and a post-render re-extraction step, and folding it naively would accrete scroll/re-extract special-casing into the dispatcher this change is cleaning. It gets its own coherent change.
- The shelf `http-fetch` DNS-verdict split (Step 0); new transport-failure planner rules (Step 2); the archive-staleness hint (Step 3).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `cascade-decision-log`: the "The orchestrator is a pure executor of planner actions" requirement tightens from "a pure executor" (today satisfied by two partial executors, neither handling the full union) to "**exactly one executor function** that handles the full `Action` union, invoked from both the tier-walk and the post-gate loop, so the escalation ladder is reachable from any post-observation position." The "Escalation is decided by a pure planner over the observation log" requirement's `Action` vocabulary list is corrected to include `EscalatePaid` (always a planner action; the prior text omitted it). The post-extraction completeness-escalation policy (obstacle/listing/`escalate_to_render`) is explicitly noted as folded into the planner by a *follow-up* change, not this one.

## Impact

- `src/a2web/fetcher.py` — `_execute_tier_action` becomes the single `_dispatch_action(fc, action, *, state, post_gate)`; the tier-loop after-tier dispatch and the post-gate `while` escalation loop both route through it. The won-tier install moves to the tier-loop call site (it is keyed on the tier result, not a planner `Action`). The `_phase_obstacle_render` / `_phase_listing_render` phases and the `render_requested` branch are UNCHANGED in this change (folded in the follow-up).
- `src/a2web/actions/playbook.py` — unchanged in this change (no new rules). `decide_next` and `_RULES` already produce `EscalatePaid`; the executor now dispatches the full union uniformly.
- No wire/envelope change, no tool-signature change, no new dependency. Verdict remains the pure projection of the decision log; browser cap (2, fast→robust) and paid cap (1) preserved; block-pages-never-cached and ADR-0009 loud-incompleteness invariants preserved.
- Tests: `tests/capabilities/cascade_decision_log/`, `tests/capabilities/quality_gate/`, `tests/capabilities/listing_completeness/`, `tests/capabilities/tier_pipeline/`, `tests/capabilities/fetch_response/`, `tests/capabilities/ask_response/` must stay green with no expectation edits that change observable output; a new test asserts the single executor dispatches every `Action` type and that `RewriteUrl` still restarts the tier walk with the 1-rewrite cap.
