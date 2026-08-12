# feedback-telemetry Specification

## Purpose
TBD - created by archiving change add-a2web-feedback-channel. Update Purpose after archive.
## Requirements
### Requirement: Feedback reporting is opt-in and off by default

a2web SHALL NOT send any feedback report unless an explicit configuration flag is enabled by the operator. In the default configuration (flag unset), a2web SHALL send no network traffic to any feedback endpoint, regardless of how many failures or `OperatorHint`s occur.

#### Scenario: Default configuration sends nothing

- **WHEN** a2web runs with the feedback flag unset (default) and a fetch produces a `critical`-severity `OperatorHint`
- **THEN** no HTTP request is made to any feedback endpoint

#### Scenario: Enabling the flag activates reporting

- **WHEN** the operator sets the feedback-enable configuration to true and a fetch produces a `warning`- or `critical`-severity `OperatorHint`
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

A feedback report SHALL include the hint `code`, `severity`, tier/handler context, and the a2web version. A feedback report SHALL NOT include the raw fetched URL, the caller's query text, or any page content/narrative body, unless a separate, independently-off-by-default "include content" setting is enabled.

#### Scenario: Default report omits URL and content

- **WHEN** feedback reporting is enabled (content-inclusion setting left at its default of off) and a report is emitted for a failed fetch
- **THEN** the outgoing payload contains no raw URL, query text, or page content fields

#### Scenario: Explicit opt-up includes content

- **WHEN** both feedback reporting and the separate content-inclusion setting are enabled
- **THEN** the outgoing payload may include the fetched URL, query, and narrative content associated with the hint

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

