# app-composition (delta — a2kit v0.43 migration)

## ADDED Requirements

### Requirement: Canonical MCP tool names pinned under flat naming

The system SHALL pin the canonical MCP name of each router verb verbatim via
`canonical_name_override`, so the wire contract is unchanged by the a2kit v0.42+
migration. (a2kit v0.42.0 / ADR-0028 derives the canonical name as
`{router.slug}_{leaf}` by default, which would otherwise rename a2web's tools to
`web_ask` / `web_fetch_raw` / `cookies_refresh`. a2web is installed globally and
wired into operators' MCP configs under the **bare** names, so the override is
load-bearing.) Specifically:

- `WebRouter.ask` SHALL expose canonical name `ask`.
- `WebRouter.fetch_raw` SHALL expose canonical name `fetch_raw`.
- `CookiesRouter.refresh` SHALL expose canonical name `refresh`.

The nested CLI surface (`a2web web ask`, `a2web cookies refresh`) SHALL be
preserved by keeping the routers in place — the override changes only the MCP
canonical name, not the CLI grouping.

#### Scenario: MCP client sees bare tool names, not flat slug-prefixed names

- **WHEN** an MCP client lists the tools exposed by `build_app()` over the
  in-process test client
- **THEN** the registered tool names include `ask`, `fetch_raw`, and `refresh`
- **AND** they do NOT include `web_ask`, `web_fetch_raw`, or `cookies_refresh`

#### Scenario: CLI grouping is preserved

- **WHEN** the CLI surface is enumerated
- **THEN** the web verbs remain grouped under `a2web web ...` and the cookie
  verb under `a2web cookies ...` (the routers are retained, not flattened to
  App-level bare verbs)
