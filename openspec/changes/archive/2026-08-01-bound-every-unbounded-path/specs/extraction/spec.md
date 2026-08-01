## ADDED Requirements

### Requirement: Every LLM call is bounded

An LLM completion request SHALL be bounded by a timeout. Exceeding it SHALL
produce a declared failure carrying an operator hint that names the timeout, and
SHALL NOT hang the tool call.

The bound SHALL be operator-configurable. A tool call that never returns is
indistinguishable to an MCP client from a2web being down, and gives the operator
no signal about which hop stalled.

Where the provider substrate cannot abort the underlying request, the bound
SHALL still be enforced at a2web's seam, and the resulting failure SHALL NOT
claim the request was cancelled upstream — only that a2web stopped waiting.

#### Scenario: A hung provider fails instead of hanging

- **WHEN** an LLM provider does not respond within the configured bound
- **THEN** extraction returns a declared failure with an operator hint naming
  the timeout, and the tool call returns

#### Scenario: The bound is operator-configurable

- **WHEN** an operator sets the LLM timeout via settings
- **THEN** that value governs, without a code change

#### Scenario: A timeout is not reported as a cancelled upstream request

- **WHEN** a2web abandons a call the provider adapter is still running
- **THEN** the failure states that a2web stopped waiting, and does not assert
  the upstream request was aborted
