## ADDED Requirements

### Requirement: Paid render escalates on a post-browser js_required SPA shell

The paid last-resort planner SHALL treat a `length_floor` gate verdict whose block-detector subsystem is `js_required` as a wall worth a paid render, dispatching the paid tier (Zyte, default `browserHtml` mode). This fires only after the free/proxied ladder — including the browser rung — is exhausted, and only within the existing single-paid-dispatch budget. The subsystem check is load-bearing: a bare `length_floor` verdict without the `js_required` subsystem (a thin article, an empty result set) MUST NOT trigger paid egress, so paid spend stays scoped to genuine JS-shell SPAs.

#### Scenario: Unrendered SPA shell after the browser rung escalates to paid render

- **WHEN** a fetch's latest gate/regate verdict is `length_floor` with subsystem `js_required`, the browser escalation rung is already spent, and the paid budget is unspent (`paid_dispatches < 1`)
- **THEN** the planner returns `EscalatePaid`
- **AND** the orchestrator dispatches the paid tier in its default browser-render mode

#### Scenario: Bare length_floor does not trigger paid egress

- **WHEN** a fetch's gate verdict is `length_floor` with no `js_required` subsystem (e.g. a genuinely short page or an empty result set)
- **THEN** the paid last-resort rule does not fire, and no paid egress occurs

#### Scenario: Paid budget cap prevents repeat dispatch

- **WHEN** a paid render has already been dispatched for the fetch (`paid_dispatches == 1`)
- **THEN** the js_required-SPA rule does not fire again, and the planner terminates (never spins)

#### Scenario: Un-keyed deployment falls through without cost

- **WHEN** the js_required-SPA condition holds but no paid tier is registered (no key configured)
- **THEN** the paid dispatch is a no-op and the fetch falls through to the never-silently-miss hint, incurring no cost
