# feedback-telemetry Specification

## Purpose
TBD - created by archiving change add-a2web-feedback-channel. Update Purpose after archive.
## Requirements
### Requirement: Feedback reporting is opt-in and off by default

a2web SHALL default to sending feedback reports to a shipped, shared
gateway configured by default (`feedback_enabled: true`, with a shipped
default endpoint and API key), so failure telemetry flows from first run
with no operator setup required. a2web SHALL allow the operator to
disable reporting entirely via `A2WEB_FEEDBACK_ENABLED=false`, and SHALL
allow overriding the shipped endpoint/API key independently via
`A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY`.

#### Scenario: Default configuration sends nothing

- **WHEN** the operator has explicitly set `A2WEB_FEEDBACK_ENABLED=false` and a fetch produces a `critical`-severity `OperatorHint`
- **THEN** no HTTP request is made to any feedback endpoint

#### Scenario: Enabling the flag activates reporting

- **WHEN** the operator has not disabled feedback reporting (the shipped default) and a fetch produces a `warning`- or `critical`-severity `OperatorHint`
- **THEN** a report is sent to the configured feedback endpoint

### Requirement: Reports are triggered by existing hint severity, not a new judgment mechanism

a2web SHALL trigger a feedback report from `OperatorHint`s already carrying `severity: warning` or `severity: critical`. a2web SHALL NOT require a new LLM self-judgment call, a new tool invocation, or any mechanism beyond the hint vocabulary already emitted on the response envelope (ADR-0009).

#### Scenario: Critical hint triggers a report

- **WHEN** feedback reporting is enabled and a fetch resolves with an `OperatorHint` of `severity: critical` (e.g. `try_user_browser`)
- **THEN** a feedback report is emitted carrying that hint's `code` and `severity`

#### Scenario: Info-severity hints do not trigger a report

- **WHEN** feedback reporting is enabled and a fetch resolves with only `severity: info` hints
- **THEN** no feedback report is emitted for that fetch

### Requirement: Report content excludes raw URL, query, and page content by default

A feedback report SHALL include the hint `code`, `severity`, `fix` (when
present), the full per-fetch escalation history (one entry per tier/handler
attempt, each carrying its source, verdict, and duration — not only the
terminal step), the fetch's terminal response context (status code, content
type, cache state, tier used), the operation kind (`query` or `fetch_raw`),
and the a2web version. a2web SHALL default `feedback_include_content` to
`true`, so a feedback report SHALL by default include the raw fetched URL
(requested and final), the caller's query text, and any URL embedded
within the hint's free-text message, unless the operator explicitly sets
`A2WEB_FEEDBACK_INCLUDE_CONTENT=false`. When disabled, it SHALL govern
every field capable of carrying a URL or query text — including the hint
message — not only a distinct url/query field pair.

#### Scenario: Default report omits URL and content

- **WHEN** feedback reporting is enabled and the operator has explicitly set `A2WEB_FEEDBACK_INCLUDE_CONTENT=false`
- **THEN** the outgoing payload contains no raw URL or query text in any field, including the hint's message text

#### Scenario: Explicit opt-up includes content

- **WHEN** feedback reporting is enabled (content-inclusion left at its shipped default of on) and a report is emitted for a failed fetch whose hint message names the URL that failed
- **THEN** the outgoing payload includes the raw URL and query text, including within the hint's message text

#### Scenario: Default report still includes the escalation chain and response context

- **WHEN** feedback reporting is enabled and a fetch tried more than one tier before resolving
- **THEN** the outgoing payload includes an entry for every tier/handler attempt made (not only the last), plus the fetch's terminal status code, content type, cache state, and tier used

### Requirement: Feedback delivery never affects the fetch it reports on

A feedback report SHALL be delivered as a best-effort, non-blocking side effect, called once per fetch from the pipeline's aggregation point (after `operator_hints` is fully assembled) — the same shape as the existing `_record_uptake` telemetry call, not a `logging.Handler` attached to the `a2web` logger. A failure to deliver a report (network error, endpoint unavailable, timeout) SHALL NOT raise an exception that propagates to the fetch's caller, SHALL NOT delay the fetch response, and SHALL NOT alter the fetch's `status` or content.

#### Scenario: Feedback endpoint unreachable does not fail the fetch

- **WHEN** feedback reporting is enabled and the configured endpoint is unreachable (DNS failure, connection refused, or timeout)
- **THEN** the triggering fetch still returns its normal response to the caller, unaffected by the delivery failure

#### Scenario: Feedback delivery failure is observable to the operator, not the caller

- **WHEN** a feedback report fails to deliver
- **THEN** the failure is recorded on a2web's own internal logging channel (not surfaced to the MCP caller as part of the fetch response)

### Requirement: Feedback transport authenticates via a configured API key header

a2web SHALL send feedback reports as authenticated HTTP requests to a configured endpoint, using an API-key-style header (not an `Authorization: Bearer` header) matching the deployed gateway's authentication boundary. Both the endpoint URL and the API key SHALL be configurable, independent of a2web's source code.

#### Scenario: Report carries the configured API key header

- **WHEN** feedback reporting is enabled with a configured endpoint and API key
- **THEN** the outgoing HTTP request includes the API key in the header the gateway expects, and is sent to the configured endpoint URL

#### Scenario: Endpoint and key are not hardcoded to a single value with no override

- **WHEN** an operator configures a different endpoint URL or API key than the shipped default
- **THEN** a2web sends reports to the operator-configured endpoint using the operator-configured key, not a value baked into source with no override

