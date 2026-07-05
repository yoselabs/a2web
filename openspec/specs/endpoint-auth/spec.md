# endpoint-auth Specification

## Purpose
TBD - created by archiving change deployable-container-ci. Update Purpose after archive.
## Requirements
### Requirement: Config-gated Google OAuth on the HTTP endpoint

When Google OAuth is configured via environment (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`), a2web SHALL register a2kit's bundled `GoogleAuth` AuthSpec on the HTTP-served surface so that reaching the served MCP endpoint requires a valid Google-authenticated principal. When it is not configured, no auth SHALL be registered and behavior SHALL be unchanged.

#### Scenario: Configured deployment requires authentication

- **WHEN** the server is started over HTTP with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` set
- **THEN** an unauthenticated request to the served MCP endpoint is rejected, and only a valid Google-authenticated principal is admitted

#### Scenario: Unconfigured deployment is unchanged

- **WHEN** the server is started with no `GOOGLE_*` env set (e.g. local stdio use)
- **THEN** no AuthSpec is registered and the endpoint behaves exactly as before this change

### Requirement: Auth secrets are environment-only

The Google client id and secret SHALL be read from the environment only and SHALL NOT be written to any config file, image layer, or committed artifact.

#### Scenario: Secrets never leave the environment

- **WHEN** Google OAuth is configured
- **THEN** the client id/secret are sourced from env vars, and no repository file or image layer contains them

### Requirement: Config-gated Google OAuth on the HTTP MCP endpoint

a2web SHALL protect its HTTP MCP endpoint with Google OAuth when, and only when,
Google OAuth is fully configured via environment. Configuration is env-only:
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a public `GOOGLE_BASE_URL` (with
optional `GOOGLE_REQUIRED_SCOPES` and `GOOGLE_REDIRECT_PATH`). When configured
and the transport is HTTP, a2web SHALL construct a FastMCP `GoogleProvider` and
serve it via `serve_process(runtime, …, mcp_options={"auth": provider})`.

#### Scenario: Configured HTTP endpoint requires authentication

- **WHEN** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_BASE_URL` are all set and a2web serves over HTTP
- **THEN** a `GoogleProvider` built from those values is passed to the MCP server as `mcp_options={"auth": provider}`, so an anonymous MCP request is rejected and a valid Google principal is admitted

#### Scenario: base_url is the public redirect origin

- **WHEN** the provider is constructed
- **THEN** its `base_url` is the operator-supplied public URL (never derived from `--host 0.0.0.0`), so the OAuth redirect matches the GCP client's authorized redirect URI

### Requirement: Unconfigured deployments are unchanged and auth-free

When Google OAuth is not configured, a2web SHALL behave exactly as before — no
auth middleware, the current `a2kit.run(app)` serve path — for every transport.
OAuth SHALL never engage on stdio or the CLI.

#### Scenario: No Google config → open endpoint, unchanged path

- **WHEN** none of the `GOOGLE_*` variables are set
- **THEN** a2web serves via the current `a2kit.run(app)` path with no auth provider, identical to pre-change behavior

#### Scenario: stdio and CLI never gate on OAuth

- **WHEN** the transport is stdio or the invocation is a CLI command
- **THEN** OAuth is not engaged regardless of `GOOGLE_*` configuration

### Requirement: Partial configuration fails loud

a2web MUST fail loudly at boot when `GOOGLE_CLIENT_ID` is set but
`GOOGLE_CLIENT_SECRET` or `GOOGLE_BASE_URL` is missing — raising an actionable
error rather than silently serving an open endpoint.

#### Scenario: Client id without secret or base_url → loud boot failure

- **WHEN** `GOOGLE_CLIENT_ID` is set but `GOOGLE_CLIENT_SECRET` or `GOOGLE_BASE_URL` is unset
- **THEN** a2web raises a boot-time error naming the missing variable(s), and does not start an unauthenticated server

### Requirement: Google secrets are env-only

No `GOOGLE_*` value SHALL be written to any repository file, YAML config, or
image layer. The values are read from the environment at boot.

#### Scenario: Secrets never persisted

- **WHEN** Google OAuth is configured
- **THEN** the `GOOGLE_CLIENT_SECRET` (and other `GOOGLE_*` values) exist only in the process environment — absent from the repo, the YAML config sources, and every Docker image layer

