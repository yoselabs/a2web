## ADDED Requirements

### Requirement: Obstacle-driven render phase

The orchestrator SHALL run an obstacle-driven render phase after answer
extraction (`_phase_extract_answer`) and before the cache write. When the `ask`
extractor reported `obstacle ∈ {empty, blocked}` (the `_INCOMPLETE_OBSTACLES`
set, shared with the retrieval-completeness logic), the phase SHALL dispatch one
paid render of the original URL via the existing `_escalate_paid` path, then —
only if the render produced new content — re-run content extraction and answer
extraction over the rendered content.

The phase SHALL fire only when ALL hold: the `ask` path is active; the obstacle
is in `_INCOMPLETE_OBSTACLES`; and `paid_dispatches < 1` (no paid render was
already spent by a gate wall or handler `escalate_to_render`). The shared
one-dispatch-per-fetch cap guarantees termination. The phase SHALL NOT re-run the
gate/escalate phase — the paid render is authoritative content, and the fresh
`obstacle` from the re-extraction is the completeness check.

The cache write SHALL run after this phase so the cache stores the final
(possibly re-rendered) body once, and a confabulated shell is never cached.

#### Scenario: Empty-obstacle ask escalates to a paid render and re-extracts

- **WHEN** an `ask` fetch over a JS-shell page passes the gate but the extractor reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier on the original URL, installs the rendered content, and re-runs answer extraction over it
- **AND** the cache stores the rendered body (not the shell)

#### Scenario: No re-render when the render adds nothing

- **WHEN** the obstacle render dispatches but the paid tier produces no new content (unavailable, or identical to the shell)
- **THEN** the original answer/content is retained and the phase makes no second dispatch (the surviving obstacle drives `retrieval_incomplete`)

#### Scenario: Healthy ask does not trigger the phase

- **WHEN** an `ask` fetch reports no obstacle (or an obstacle outside `{empty, blocked}`)
- **THEN** the obstacle render phase is a no-op and no paid egress occurs
