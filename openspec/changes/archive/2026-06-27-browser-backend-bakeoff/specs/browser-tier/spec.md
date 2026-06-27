## MODIFIED Requirements

### Requirement: Browser tier is in REGISTRY but not in TIER_ORDER

The system SHALL register two browser-class tiers in `REGISTRY` — `"browser"` (the fast Chromium rung) and `"browser_robust"` (the robust CDP rung) — and SHALL NOT include either in `TIER_ORDER`. Default fetches SHALL never invoke a browser tier; both are dispatched out-of-band by the orchestrator. `"browser"` is dispatched when the gate sets `suggested_tier == "browser"`; `"browser_robust"` is dispatched only when the gate *still* wants browser after the fast rung already ran (a fast render that came back thin/blocked). Each rung SHALL be capped at one dispatch per fetch.

#### Scenario: TIER_ORDER excludes both browser rungs

- **WHEN** the registry is imported
- **THEN** `"browser" in REGISTRY` and `"browser_robust" in REGISTRY`, and neither `"browser"` nor `"browser_robust"` is in `TIER_ORDER`

## ADDED Requirements

### Requirement: Browser rendering escalates fast-to-robust by reusing the existing playbook

The system SHALL realize fast→robust browser rendering as a two-rung escalation on the **existing** decision-log playbook, reusing the existing `EscalateBrowser` action and browser-escalation rule — not a separate ladder mechanism, a new action, or a new rule. The browser-escalation rule's cap SHALL be widened so the browser escalation may fire up to twice per fetch. The fast rung (`browser`, a Chromium engine) SHALL be dispatched first; because a successful fast render makes the gate verdict `ok`, the rule (which requires a non-`ok` verdict) SHALL NOT re-fire after a good fast render. When the fast render is thin/blocked the gate still wants browser, so the same rule fires again and the orchestrator dispatches the robust rung (`browser_robust`, the CDP engine). The single browser-escalation handler SHALL select the rung from the per-fetch browser-dispatch count (first → fast, second → robust). The robust rung SHALL NOT run unless the fast rung already ran. The tier/engine that produced each render SHALL be recorded in the decision log and tier events under its real name (`browser`/`browser_robust`, `patchright`/`zendriver`), never a hardcoded engine label.

#### Scenario: fast rung handles a readable SPA alone

- **WHEN** the gate signals `suggested_tier == "browser"` and the fast (`browser`) rung renders content that clears the quality gate
- **THEN** the gate verdict is `ok`, the browser rule does not re-fire, no `browser_robust` dispatch occurs, and the decision log shows the `browser` rung as the producer

#### Scenario: robust rung escalates a thin fast render

- **WHEN** the fast (`browser`) rung already ran this fetch and the gate's re-evaluation still wants browser (thin/blocked)
- **THEN** the existing `EscalateBrowser` rule fires again (cap permits a second dispatch), the orchestrator dispatches the `browser_robust` rung, and the decision log distinguishes the two rungs by name

#### Scenario: robust rung never precedes the fast rung

- **WHEN** no `browser` dispatch has occurred this fetch
- **THEN** the browser-escalation handler dispatches the fast rung (the robust rung is reachable only as the second browser dispatch)
