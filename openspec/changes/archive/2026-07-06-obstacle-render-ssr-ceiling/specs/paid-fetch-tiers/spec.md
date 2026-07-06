## MODIFIED Requirements

### Requirement: Paid render escalates on an extractor obstacle

The paid last-resort tier SHALL gain a third trigger, alongside the gate-wall
(`paid_last_resort`) and handler `escalate_to_render` triggers: an `ask`
extractor `obstacle ∈ {empty, blocked}`. When the extractor reports such an
obstacle, no paid render was already spent (`paid_dispatches < 1`), AND there is
evidence a render would add content — the already-extracted content is THIN
(`len(content_md) < _RENDER_CONTENT_CEILING`, so plausibly an unrendered shell
rather than a complete SSR/static page that merely lacks the answer), the
content did NOT come from a JS-executing tier (`jina` / `browser` /
`browser_robust`), AND the raw body shows unrendered-SPA markers
(`block_detector.looks_like_unrendered_spa`) — the orchestrator SHALL dispatch
the paid tier (Zyte, default `browserHtml` mode) on the original URL. All three
triggers share the single one-dispatch-per-fetch budget. `paywalled` / `error`
obstacles SHALL NOT trigger a paid render, and neither SHALL a content-rich page
(SSR or static) that merely lacks the answer.

#### Scenario: Thin SPA shell dispatches the paid render

- **WHEN** an `ask` extractor reports `obstacle` in `{empty, blocked}` over thin content from a non-JS tier bearing unrendered-SPA markers, a paid tier is registered, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier in its default browser-render mode on the original URL

#### Scenario: Content-rich SSR page does not dispatch a render

- **WHEN** an `ask` extractor reports `obstacle: "empty"` over an SSR page whose extracted content is at or above the ceiling (complete content, SPA markers present)
- **THEN** the obstacle trigger does not fire, no paid egress occurs, and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Paid budget is shared across triggers

- **WHEN** a paid render was already dispatched by a gate wall or handler `escalate_to_render` (`paid_dispatches == 1`) and the extractor then reports `obstacle: "empty"`
- **THEN** no second paid render is dispatched (the shared cap holds)
