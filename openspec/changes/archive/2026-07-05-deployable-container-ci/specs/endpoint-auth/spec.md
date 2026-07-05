## ADDED Requirements

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
