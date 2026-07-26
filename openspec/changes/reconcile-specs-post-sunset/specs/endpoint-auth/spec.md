## MODIFIED Requirements

### Requirement: Config-gated Google OAuth on the HTTP endpoint

When Google OAuth is configured via environment (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`), a2web's `serve_http_main()` SHALL register a FastMCP Google OAuth provider on the HTTP-served surface by passing it to `build_mcp_server(auth=provider)`, so that reaching the served MCP endpoint requires a valid Google-authenticated principal. When it is not configured, no auth provider SHALL be passed and behavior SHALL be unchanged.

#### Scenario: Configured deployment requires authentication

- **WHEN** the server is started over HTTP with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` set
- **THEN** an unauthenticated request to the served MCP endpoint is rejected, and only a valid Google-authenticated principal is admitted

#### Scenario: Unconfigured deployment is unchanged

- **WHEN** the server is started with no `GOOGLE_*` env set (e.g. local stdio use)
- **THEN** no auth provider is passed to `build_mcp_server` and the endpoint behaves exactly as before this change

### Requirement: Config-gated Google OAuth on the HTTP MCP endpoint

a2web SHALL protect its HTTP MCP endpoint with Google OAuth when, and only when,
Google OAuth is fully configured via environment. Configuration is env-only:
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a public `GOOGLE_BASE_URL` (with
optional `GOOGLE_REQUIRED_SCOPES` and `GOOGLE_REDIRECT_PATH`). When configured
and the transport is HTTP, `serve_http_main()` SHALL construct a FastMCP
`GoogleProvider` and serve it via `build_mcp_server(auth=provider)` →
`mcp.run(transport="http")`.

#### Scenario: Configured HTTP endpoint requires authentication

- **WHEN** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_BASE_URL` are all set and a2web serves over HTTP
- **THEN** a `GoogleProvider` built from those values is passed to `build_mcp_server(auth=provider)`, so an anonymous MCP request is rejected and a valid Google principal is admitted

#### Scenario: base_url is the public redirect origin

- **WHEN** the provider is constructed
- **THEN** its `base_url` is the operator-supplied public URL (never derived from `--host 0.0.0.0`), so the OAuth redirect matches the GCP client's authorized redirect URI

### Requirement: Unconfigured deployments are unchanged and auth-free

When Google OAuth is not configured, a2web SHALL behave exactly as before — no
auth middleware, the current `serve_http_main()` → `mcp.run(transport="http")`
serve path with no `auth=` provider — for every transport. OAuth SHALL never
engage on stdio or the CLI.

#### Scenario: No Google config → open endpoint, unchanged path

- **WHEN** none of the `GOOGLE_*` variables are set
- **THEN** a2web serves via the current `serve_http_main()` → `mcp.run(transport="http")` path with no auth provider, identical to pre-change behavior

#### Scenario: stdio and CLI never gate on OAuth

- **WHEN** the transport is stdio or the invocation is a CLI command
- **THEN** OAuth is not engaged regardless of `GOOGLE_*` configuration
