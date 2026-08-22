## Purpose

Gives the calling agent a standing, connection-time rule for handling a `severity: critical` operator hint, delivered outside the per-fetch response so it survives being buried under later tool results.

## ADDED Requirements

### Requirement: Server declares a critical-hint compliance instruction at connection

The a2web MCP server SHALL set a non-empty `instructions` string on its `FastMCP` server declaration, returned to clients via the MCP `initialize` handshake (`InitializeResult.instructions`).

The instructions string SHALL direct the calling agent to try every available browser tool — not only the first one attempted — before concluding a URL carrying a `severity: critical` operator hint is unreachable. It SHALL NOT restate the remediation text already carried in `operator_hints[].fix` for existing hints (e.g. `try_user_browser_hint`); it exists to name the specific compliance failure (stopping after one tool) that per-hint text does not address.

#### Scenario: Instructions are present in the initialize handshake

- **WHEN** an MCP client completes the `initialize` handshake with the a2web server
- **THEN** the response's `instructions` field is a non-empty string

#### Scenario: Instructions name the multi-tool-check rule

- **WHEN** the `instructions` string is inspected
- **THEN** it directs the reader to try every available browser tool before treating a critical-severity hint's URL as unreachable, and does not merely repeat "open a real browser tool"
