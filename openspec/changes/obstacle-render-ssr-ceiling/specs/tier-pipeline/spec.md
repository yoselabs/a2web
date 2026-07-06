## MODIFIED Requirements

### Requirement: Obstacle-driven render phase

The orchestrator SHALL run an obstacle-driven render phase after answer
extraction (`_phase_extract_answer`) and before the cache write. When the `ask`
extractor reported `obstacle ∈ {empty, blocked}` (the `_INCOMPLETE_OBSTACLES`
set, shared with the retrieval-completeness logic), the phase SHALL dispatch one
paid render of the original URL via the existing `_escalate_paid` path, then —
only if the render produced new content — re-run content extraction and answer
extraction over the rendered content.

The phase SHALL fire only when ALL hold: the `ask` path is active; the obstacle
is in `_INCOMPLETE_OBSTACLES`; `paid_dispatches < 1`; **the already-extracted
content is THIN** (`len(content_md) < _RENDER_CONTENT_CEILING`, 2000 chars — a
content-rich page is complete, so the answer's absence is real and a render
can't add it; this is the load-bearing SSR guard: Next/Nuxt sites carry SPA
mount markers yet already contain their content); the content did NOT come from
a JS-executing tier (`jina` / `browser` / `browser_robust`); AND the raw body
shows unrendered-SPA markers (`block_detector.looks_like_unrendered_spa`). The
shared one-dispatch-per-fetch cap guarantees termination. The phase SHALL NOT
re-run the gate/escalate phase — the paid render is authoritative content, and
the fresh `obstacle` from the re-extraction is the completeness check.

#### Scenario: Thin SPA shell escalates to a paid render

- **WHEN** an `ask` fetch over a JS-shell page (thin `content_md`, unrendered-SPA markers, non-JS tier) passes the gate but the extractor reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier on the original URL and re-runs answer extraction over the rendered content

#### Scenario: Content-rich SSR page with SPA markers does NOT render

- **WHEN** an `ask` fetch over an SSR framework page (SPA mount markers present, but substantial extracted content ≥ the ceiling) reports `obstacle: "empty"` because the answer genuinely isn't present
- **THEN** no paid render is dispatched (the page is complete; a render can't add the missing answer), and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Content from a JS-executing tier does NOT re-render

- **WHEN** the winning content came from `jina` / `browser` / `browser_robust` and the extractor reports `obstacle: "empty"`
- **THEN** no obstacle-driven paid render is dispatched

#### Scenario: Healthy ask does not trigger the phase

- **WHEN** an `ask` fetch reports no obstacle (or an obstacle outside `{empty, blocked}`)
- **THEN** the obstacle render phase is a no-op and no paid egress occurs
