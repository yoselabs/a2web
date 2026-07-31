# endpoint-auth Specification

## Purpose
TBD - created by archiving change deployable-container-ci. Update Purpose after archive.
## Requirements
### Requirement: Config-gated Google OAuth on the HTTP endpoint

When Google OAuth is configured via environment (`A2WEB_GOOGLE_CLIENT_ID` / `A2WEB_GOOGLE_CLIENT_SECRET`), a2web's `serve_http_main()` SHALL register a FastMCP Google OAuth provider on the HTTP-served surface by passing it to `build_mcp_server(auth=provider)`, so that reaching the served MCP endpoint requires a valid Google-authenticated principal. When it is not configured, no auth provider SHALL be passed and behavior SHALL be unchanged.

#### Scenario: Configured deployment requires authentication

- **WHEN** the server is started over HTTP with `A2WEB_GOOGLE_CLIENT_ID` and `A2WEB_GOOGLE_CLIENT_SECRET` set
- **THEN** an unauthenticated request to the served MCP endpoint is rejected, and only a valid Google-authenticated principal is admitted

#### Scenario: Unconfigured deployment is unchanged

- **WHEN** the server is started with no `A2WEB_GOOGLE_*` env set (e.g. local stdio use)
- **THEN** no auth provider is passed to `build_mcp_server` and the endpoint behaves exactly as before this change

### Requirement: Auth secrets are environment-only

The Google client id and secret SHALL be read from the environment only and SHALL NOT be written to any config file, image layer, or committed artifact.

#### Scenario: Secrets never leave the environment

- **WHEN** Google OAuth is configured
- **THEN** the client id/secret are sourced from env vars, and no repository file or image layer contains them

### Requirement: Config-gated Google OAuth on the HTTP MCP endpoint

a2web SHALL protect its HTTP MCP endpoint with Google OAuth when, and only when,
Google OAuth is fully configured via environment. Configuration is env-only:
`A2WEB_GOOGLE_CLIENT_ID`, `A2WEB_GOOGLE_CLIENT_SECRET`, and a public `A2WEB_GOOGLE_BASE_URL` (with
optional `A2WEB_GOOGLE_REQUIRED_SCOPES` and `A2WEB_GOOGLE_REDIRECT_PATH`). When configured
and the transport is HTTP, `serve_http_main()` SHALL construct a FastMCP
`GoogleProvider` and serve it via `build_mcp_server(auth=provider)` →
`mcp.run(transport="http")`.

#### Scenario: Configured HTTP endpoint requires authentication

- **WHEN** `A2WEB_GOOGLE_CLIENT_ID`, `A2WEB_GOOGLE_CLIENT_SECRET`, and `A2WEB_GOOGLE_BASE_URL` are all set and a2web serves over HTTP
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

- **WHEN** none of the `A2WEB_GOOGLE_*` variables are set
- **THEN** a2web serves via the current `serve_http_main()` → `mcp.run(transport="http")` path with no auth provider, identical to pre-change behavior

#### Scenario: stdio and CLI never gate on OAuth

- **WHEN** the transport is stdio or the invocation is a CLI command
- **THEN** OAuth is not engaged regardless of `A2WEB_GOOGLE_*` configuration

### Requirement: Partial configuration fails loud

a2web MUST fail loudly at boot when `A2WEB_GOOGLE_CLIENT_ID` is set but
`A2WEB_GOOGLE_CLIENT_SECRET` or `A2WEB_GOOGLE_BASE_URL` is missing — raising an actionable
error rather than silently serving an open endpoint.

#### Scenario: Client id without secret or base_url → loud boot failure

- **WHEN** `A2WEB_GOOGLE_CLIENT_ID` is set but `A2WEB_GOOGLE_CLIENT_SECRET` or `A2WEB_GOOGLE_BASE_URL` is unset
- **THEN** a2web raises a boot-time error naming the missing variable(s), and does not start an unauthenticated server

### Requirement: Google secrets are env-only

No `A2WEB_GOOGLE_*` value SHALL be written to any repository file, YAML config, or
image layer. The values are read from the environment at boot.

#### Scenario: Secrets never persisted

- **WHEN** Google OAuth is configured
- **THEN** the `A2WEB_GOOGLE_CLIENT_SECRET` (and other `A2WEB_GOOGLE_*` values) exist only in the process environment — absent from the repo, the YAML config sources, and every Docker image layer


### Requirement: Unprefixed auth configuration fails closed

a2web SHALL refuse to start when auth environment variables are set WITHOUT the
`A2WEB_` prefix and no prefixed auth variable is set. `AppSettings` reads env
with `env_prefix="A2WEB_"` and `extra="ignore"`, so a bare `GOOGLE_CLIENT_ID`
populates nothing: without this check an operator who configures auth with the
unprefixed names serves an **unauthenticated** endpoint while every
operator-visible signal reports it configured. The partial-configuration guard
cannot catch this case — from inside `AppSettings`, nothing was configured at
all.

The check SHALL be narrow: it fires only when no prefixed auth variable is
present and at least one bare one is, so a correctly-prefixed deployment that
also carries an unrelated `GOOGLE_CLIENT_ID` still boots. The error SHALL name
the correct prefixed spelling, not merely reject the wrong one.

#### Scenario: Bare auth vars → loud boot failure, never an open endpoint

- **WHEN** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_BASE_URL` are set without the `A2WEB_` prefix and no `A2WEB_GOOGLE_*` variable is set
- **THEN** a2web raises a boot-time error naming both the offending variables and their `A2WEB_`-prefixed spellings, and does not start an unauthenticated server

#### Scenario: An unrelated bare var does not break a correct deployment

- **WHEN** `A2WEB_GOOGLE_CLIENT_ID` / `A2WEB_GOOGLE_CLIENT_SECRET` / `A2WEB_GOOGLE_BASE_URL` are all set and an unrelated bare `GOOGLE_CLIENT_ID` is also present
- **THEN** the prefixed values win, the provider is constructed, and no error is raised

#### Scenario: Deliberate open deployment is unaffected

- **WHEN** no auth variable is set in either spelling
- **THEN** a2web serves open exactly as before, with no auth provider and no boot failure
