## ADDED Requirements

### Requirement: Listing-completeness phase and escalation trigger

The pipeline SHALL run a listing-completeness assessment after record extraction:
it compares the parsed record count against the generic item oracle via
`content_expectations.assess` and, on a `partial` verdict, attaches the
`listing_partial` signal. When listing completion is enabled and the partial
listing was served by a non-scrolling tier (raw/jina), the `partial` verdict
SHALL act as an escalation trigger requesting a scrolling render — reusing the
`escalate_to_render` / `_escalate_paid` path and sharing the single
one-paid-dispatch-per-fetch cap with the gate-wall and obstacle triggers. The
phase performs no fetching when completion is disabled (signal-only).

#### Scenario: Completeness phase runs after extraction

- **WHEN** a fetch has extracted records and computed a listing verdict
- **THEN** a `partial` verdict attaches the `listing_partial` signal before the response is built

#### Scenario: Partial listing on a non-scrolling tier escalates

- **WHEN** completion is enabled, the verdict is `partial`, the tier was raw/jina, and no render was yet spent
- **THEN** the pipeline requests a scrolling render through the shared render path and one paid dispatch (at most) is consumed

#### Scenario: Signal-only when completion is disabled

- **WHEN** completion is disabled and the verdict is `partial`
- **THEN** the `listing_partial` signal is attached and no render is dispatched
