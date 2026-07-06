## MODIFIED Requirements

### Requirement: Paid render escalates on an extractor obstacle

The paid last-resort tier SHALL gain a third trigger, alongside the gate-wall
(`paid_last_resort`) and handler `escalate_to_render` triggers: an `ask`
extractor `obstacle ∈ {empty, blocked}`. When the extractor reports such an
obstacle, no paid render was already spent (`paid_dispatches < 1`), AND there is
evidence a render would add content — the content did NOT come from a
JS-executing tier (`jina` / `browser` / `browser_robust`) AND the raw body shows
unrendered-SPA markers (`block_detector.looks_like_unrendered_spa`) — the
orchestrator SHALL dispatch the paid tier (Zyte, default `browserHtml` mode) on
the original URL. All three triggers share the single one-dispatch-per-fetch
budget, so at most one paid render occurs regardless of how many triggers fire.
`paywalled` / `error` obstacles SHALL NOT trigger a paid render, and neither
SHALL a complete static page that merely lacks the answer (no SPA markers).

#### Scenario: Empty/blocked obstacle on an SPA shell dispatches the paid render

- **WHEN** an `ask` extractor reports `obstacle` in `{empty, blocked}` over content from a non-JS tier bearing unrendered-SPA markers, a paid tier is registered, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier in its default browser-render mode on the original URL

#### Scenario: Static page lacking the answer does not dispatch a render

- **WHEN** an `ask` extractor reports `obstacle: "empty"` over a complete static page with no unrendered-SPA markers
- **THEN** the obstacle trigger does not fire, no paid egress occurs, and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Content from a JS-executing tier does not dispatch a render

- **WHEN** the winning content came from `jina` / `browser` / `browser_robust` and the extractor reports `obstacle: "empty"`
- **THEN** the obstacle trigger does not fire (a re-render would return the same content)

#### Scenario: Paid budget is shared across triggers

- **WHEN** a paid render was already dispatched by a gate wall or handler `escalate_to_render` (`paid_dispatches == 1`) and the extractor then reports `obstacle: "empty"`
- **THEN** no second paid render is dispatched (the shared cap holds)
