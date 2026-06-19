# app-composition (delta — a2kit v0.44 migration)

## ADDED Requirements

### Requirement: MCP wire contract survives a2kit substrate upgrades

The a2web MCP wire contract SHALL be invariant across a2kit dependency upgrades:
the installed binary serves over **stdio** and exposes the **bare** tool names
`ask`, `fetch_raw`, and `refresh`. An a2kit version bump SHALL NOT alter the
transport, the tool names, or the input schemas as observed by an MCP client.
(a2web is installed globally and wired into operators' MCP configs under these
names over stdio; a regression on either silently breaks every installed client.
This requirement makes contract-preservation an explicit gate on every future
substrate bump, not an incidental property.)

A substrate upgrade that would change the contract SHALL be treated as a real
migration — the canonical-name pins (`canonical_name_override`) and the stdio
entrypoint (`a2kit.run(app)` with `args: ["serve"]`) are load-bearing and SHALL
be re-verified, not assumed, after each bump.

#### Scenario: bare tool names survive the a2kit v0.44 bump

- **WHEN** an MCP client lists the tools exposed by `build_app()` over the
  in-process test client after the pin moves to a2kit v0.44
- **THEN** the registered tool names include `ask`, `fetch_raw`, and `refresh`
- **AND** they do NOT include `web_ask`, `web_fetch_raw`, or `cookies_refresh`

#### Scenario: transport is unchanged by the bump

- **WHEN** the installed binary is launched with `args: ["serve"]` after the
  a2kit v0.44 bump
- **THEN** it serves MCP over stdio (no http transport is configured or required)
