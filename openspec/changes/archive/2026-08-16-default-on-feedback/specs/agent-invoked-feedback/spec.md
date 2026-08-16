## MODIFIED Requirements

### Requirement: Agent feedback reuses the existing feedback transport and gating

a2web SHALL deliver `report_feedback` reports through the same opt-in,
non-blocking OTLP transport `feedback-telemetry` already uses, gated by the
same `A2WEB_FEEDBACK_ENABLED`/`A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY`
configuration — which SHALL default to a shipped, shared gateway
(`feedback_enabled: true` with a shipped default endpoint and API key), not
to off. a2web SHALL NOT introduce a second transport, endpoint, or
credential surface for this capability.

#### Scenario: Feedback flag off means report_feedback sends nothing

- **WHEN** the operator has explicitly set `A2WEB_FEEDBACK_ENABLED=false` and an agent calls `report_feedback`
- **THEN** no HTTP request is made to any endpoint

#### Scenario: Reports are distinguishable from mechanical reports on the same stream

- **WHEN** feedback reporting is enabled and an agent calls `report_feedback`
- **THEN** the outgoing report is distinguishable (e.g. by scope name) from a2web's own mechanical `feedback-telemetry` reports on the same stream

### Requirement: The tool is implemented by the shared shelf package, not a2web-local code

a2web SHALL mount `report_feedback` via the shelf `mcp-feedback` package's
`register_feedback_tool`, passing its own resolved
`A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY` settings (defaulting to
the shipped shared gateway) and a fixed `extra_instructions` string naming
its own convention ("subject = the URL you fetched") plus a disclosure
sentence stating that feedback reporting is on by default and naming the
`A2WEB_FEEDBACK_ENABLED=false` opt-out. a2web SHALL NOT maintain a second,
a2web-local implementation of the agent-invoked feedback tool's schema or
transport.

#### Scenario: a2web contributes only config and one line of guidance

- **WHEN** inspecting a2web's registration of `report_feedback`
- **THEN** the call site passes only `endpoint`, `api_key`, and `extra_instructions` — no tool schema, transport, or field logic is defined in a2web

#### Scenario: The tool description discloses the default-on behavior

- **WHEN** an MCP client lists tools and inspects `report_feedback`'s description
- **THEN** the description states that feedback reporting is on by default and names the `A2WEB_FEEDBACK_ENABLED=false` opt-out

## ADDED Requirements

### Requirement: Fetch tools disclose default-on reporting in their own descriptions

`query` and `fetch_raw` SHALL each carry a short sentence in their tool
description disclosing that a2web reports its own failures by default and
naming the `A2WEB_FEEDBACK_ENABLED=false` opt-out — since the mechanical
`feedback-telemetry` reporter can fire from either tool without the agent
ever calling `report_feedback`. a2web SHALL NOT rely on an MCP resource or
skill as the disclosure mechanism, since `resources/list` is optional in
the MCP specification and not universally implemented by clients, unlike
`tools/list`.

#### Scenario: query and fetch_raw both disclose the default

- **WHEN** an MCP client lists tools and inspects `query` and `fetch_raw`'s descriptions
- **THEN** both mention that a2web reports its own failures by default and name the opt-out env var

#### Scenario: cookies_refresh carries no such disclosure

- **WHEN** an MCP client inspects `cookies_refresh`'s description
- **THEN** it contains no feedback-reporting disclosure, since that tool never triggers the mechanical reporter
