## MODIFIED Requirements

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
