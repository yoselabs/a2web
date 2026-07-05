## ADDED Requirements

### Requirement: Paid render escalates on an extractor obstacle

The paid last-resort tier SHALL gain a third trigger, alongside the gate-wall
(`paid_last_resort`) and handler `escalate_to_render` triggers: an `ask`
extractor `obstacle ∈ {empty, blocked}`. When the extractor reports such an
obstacle and no paid render was already spent (`paid_dispatches < 1`), the
orchestrator SHALL dispatch the paid tier (Zyte, default `browserHtml` mode) on
the original URL. All three triggers share the single one-dispatch-per-fetch
budget, so at most one paid render occurs regardless of how many triggers fire.
`paywalled` / `error` obstacles SHALL NOT trigger a paid render.

#### Scenario: Empty/blocked obstacle dispatches the paid render

- **WHEN** an `ask` extractor reports `obstacle` in `{empty, blocked}`, a paid tier is registered, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier in its default browser-render mode on the original URL

#### Scenario: Paid budget is shared across triggers

- **WHEN** a paid render was already dispatched by a gate wall or handler `escalate_to_render` (`paid_dispatches == 1`) and the extractor then reports `obstacle: "empty"`
- **THEN** no second paid render is dispatched (the shared cap holds)

#### Scenario: Paywalled obstacle does not dispatch a paid render

- **WHEN** an `ask` extractor reports `obstacle: "paywalled"`
- **THEN** the obstacle trigger does not fire (a render won't clear a paywall)

#### Scenario: Un-keyed deployment falls through without cost

- **WHEN** the obstacle condition holds but no paid tier is registered
- **THEN** no paid egress occurs and the surviving obstacle drives `retrieval_incomplete`
