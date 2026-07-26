## ADDED Requirements

### Requirement: A tool failure delivers the real error envelope on both channels

When a tool body raises, the MCP response SHALL carry the actual failure
information — not a framework-internal exception string. Specifically the
response SHALL set `is_error` true, SHALL place the real error prose in
`content[].text`, and SHALL populate `structured_content` with the error
envelope. `structured_content` SHALL NOT be null on a tool failure.

This is the transport-level guarantee that ADR-0009 depends on: a walled or
failed fetch must reach the caller as an explicit, legible incompleteness. An
error path that substitutes a framework `TypeError` for the real envelope makes
a wall indistinguishable from an a2web bug, and the caller cannot tell that a
retrieval was attempted at all.

#### Scenario: A tool-body exception surfaces the real message

- **WHEN** a tool body raises an exception during an MCP call
- **THEN** the response has `is_error` true, `content[0].text` contains the real
  exception prose, and `structured_content` is not null

#### Scenario: An unexpected fault names its real cause

- **WHEN** a fault the application did not anticipate occurs while serving a
  fetch
- **THEN** the structured error identifies the underlying exception type and its
  message, so the caller can distinguish an application fault from a retrieval
  obstacle

> Note: a walled or failed *retrieval* is not an error path. It returns
> successfully carrying `status: failed` + `retrieval_incomplete: true` +
> diagnostics + narrative + a critical operator hint, per ADR-0009. The error
> envelope covers only unanticipated faults. Both must be legible; they are
> different mechanisms, and conflating them was an error in the first draft of
> this spec.

#### Scenario: Argument-validation errors are unaffected

- **WHEN** a tool is called with a required argument missing
- **THEN** the framework-owned validation error is returned unchanged — this
  change does not alter the validation path

### Requirement: The resolved MCP substrate supports the error-envelope API

The dependency set SHALL resolve to a FastMCP version whose `ToolResult`
constructor accepts the error flag used by the error-envelope middleware. A
resolved combination in which the middleware passes an argument the constructor
rejects SHALL be treated as a build failure, not a runtime degradation.

#### Scenario: The resolved substrate is compatible

- **WHEN** dependencies are locked and installed
- **THEN** the resolved FastMCP version's `ToolResult` accepts the error flag the
  error-envelope path passes
