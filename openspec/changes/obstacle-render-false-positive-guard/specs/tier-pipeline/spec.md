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
is in `_INCOMPLETE_OBSTACLES`; `paid_dispatches < 1` (no paid render was already
spent by a gate wall or handler `escalate_to_render`); **and there is evidence a
render would add content** — the content did NOT come from a JS-executing tier
(`jina` / `browser` / `browser_robust`, which already ran JS so a re-render is
redundant) AND the raw body shows unrendered-SPA markers (a root mount plus
`<script>` tags, via `block_detector.looks_like_unrendered_spa`). A complete
static page with no such markers (a spec doc, a book) that simply lacks the
answer SHALL NOT trigger a render, even on `obstacle: empty`. The shared
one-dispatch-per-fetch cap guarantees termination. The phase SHALL NOT re-run the
gate/escalate phase — the paid render is authoritative content, and the fresh
`obstacle` from the re-extraction is the completeness check.

#### Scenario: Empty-obstacle ask over an SPA shell escalates to a paid render

- **WHEN** an `ask` fetch over a JS-shell page (unrendered-SPA markers, from a non-JS tier) passes the gate but the extractor reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier on the original URL and re-runs answer extraction over the rendered content

#### Scenario: Empty obstacle on a complete static page does NOT render

- **WHEN** an `ask` fetch over a complete static page with NO unrendered-SPA markers (e.g. a spec document) reports `obstacle: "empty"` because the answer genuinely isn't present
- **THEN** no paid render is dispatched (a render can't add the missing answer), and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Content from a JS-executing tier does NOT re-render

- **WHEN** the winning content came from `jina` / `browser` / `browser_robust` (JS already executed) and the extractor still reports `obstacle: "empty"`
- **THEN** no obstacle-driven paid render is dispatched (a re-render would return the same content)

#### Scenario: Healthy ask does not trigger the phase

- **WHEN** an `ask` fetch reports no obstacle (or an obstacle outside `{empty, blocked}`)
- **THEN** the obstacle render phase is a no-op and no paid egress occurs
