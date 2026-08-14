## Purpose

Lets the calling agent report its own subjective read on a fetch —
content that's mechanically fine but wrong for what it actually needed —
a class of failure a2web's own pipeline has no signal to detect on its own.

## ADDED Requirements

### Requirement: A dedicated tool accepts free-text agent feedback, not a closed category

a2web SHALL expose a `report_feedback` tool accepting a `url` (the fetch
being reported on), a `note` (free text — what bothered the agent), and an
optional `wanted` (free text — what it would have preferred). a2web SHALL
NOT require the caller to select from a closed category/taxonomy for the
nature of the complaint.

#### Scenario: Agent reports dissatisfaction with a mechanically successful fetch

- **WHEN** an agent calls `report_feedback` with a `url` from a prior fetch, a `note` describing what was wrong, and no `wanted`
- **THEN** the report is accepted without requiring a category selection

#### Scenario: Agent optionally states what it wanted instead

- **WHEN** an agent calls `report_feedback` with both `note` and `wanted` populated
- **THEN** both are carried on the outgoing report as distinct fields

### Requirement: The tool is discovered via an in-response nudge, not a load-time description alone

a2web SHALL surface an inline nudge toward `report_feedback` on responses
that already carry a warning- or critical-severity `OperatorHint`, appended
to that hint's existing remediation text. a2web SHALL NOT rely solely on
the tool's load-time description for discovery.

#### Scenario: A warning/critical hint carries the nudge

- **WHEN** a fetch resolves with a warning- or critical-severity `OperatorHint`
- **THEN** the hint's remediation text includes a pointer to `report_feedback` as an available next step

### Requirement: A confidence-only deviation also nudges, even with no hint

a2web SHALL surface the `report_feedback` nudge on a fetch that resolves
with `confidence: low`, even when no `OperatorHint` fired, by carrying one
additional info-severity hint for that purpose.

#### Scenario: Low confidence with no hint still nudges

- **WHEN** a fetch resolves with `status: ok` and `confidence: low`, and no `OperatorHint` was otherwise emitted
- **THEN** the response carries exactly one hint whose purpose is pointing at `report_feedback`

### Requirement: A mechanically clean, high-confidence fetch never nudges

a2web SHALL NOT emit a `report_feedback` nudge, and SHALL NOT add any
`OperatorHint` for that purpose, on a fetch that resolves with `status: ok`
and `confidence: high`.

#### Scenario: Silent success stays silent

- **WHEN** a fetch resolves with `status: ok` and `confidence: high`
- **THEN** the response carries no hint pointing at `report_feedback`, and no other envelope field changes as a result of this capability

### Requirement: Agent feedback correlates to the mechanical report by URL, not a new identifier

a2web SHALL correlate a `report_feedback` call to any mechanical
`feedback-telemetry` report for the same fetch using the `url` field alone.
a2web SHALL NOT require a separate correlation identifier on the fetch
response for this purpose.

#### Scenario: No new response field is required for correlation

- **WHEN** an agent calls `report_feedback` referencing a `url` it received from a prior fetch response
- **THEN** the call succeeds without any additional identifier having been returned by that prior response

### Requirement: Agent feedback reuses the existing feedback transport and gating

a2web SHALL deliver `report_feedback` reports through the same opt-in,
non-blocking OTLP transport `feedback-telemetry` already uses, gated by the
same `A2WEB_FEEDBACK_ENABLED`/`A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY`
configuration. a2web SHALL NOT introduce a second transport, endpoint, or
credential surface for this capability.

#### Scenario: Feedback flag off means report_feedback sends nothing

- **WHEN** `A2WEB_FEEDBACK_ENABLED` is unset (default) and an agent calls `report_feedback`
- **THEN** no HTTP request is made to any endpoint

#### Scenario: Reports are distinguishable from mechanical reports on the same stream

- **WHEN** feedback reporting is enabled and an agent calls `report_feedback`
- **THEN** the outgoing report is distinguishable (e.g. by scope name) from a2web's own mechanical `feedback-telemetry` reports on the same stream

### Requirement: Agent-supplied fields are not gated by the content-inclusion setting

a2web SHALL send `report_feedback`'s `url`, `note`, and `wanted` regardless
of `A2WEB_FEEDBACK_INCLUDE_CONTENT`, since the agent explicitly supplies
them as tool arguments rather than a2web deciding to send them passively.

#### Scenario: url is sent even with content-inclusion off

- **WHEN** `A2WEB_FEEDBACK_INCLUDE_CONTENT` is unset (default) and feedback reporting is enabled, and an agent calls `report_feedback`
- **THEN** the outgoing report includes the `url` the agent supplied
