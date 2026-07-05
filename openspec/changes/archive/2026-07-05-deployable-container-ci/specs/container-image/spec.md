## ADDED Requirements

### Requirement: Reproducible slim image with a networked entrypoint

The repository SHALL provide a `Dockerfile` producing an image that installs a2web and its runtime dependencies reproducibly from the lockfile, runs as a **non-root** user, and whose default command starts the HTTP-transport server (`serve --transport=http --host=0.0.0.0`) so the MCP surface is reachable over the network at `/mcp`.

#### Scenario: Container serves MCP over HTTP

- **WHEN** the image is run with no command override
- **THEN** the process starts `a2web serve --transport=http` bound to `0.0.0.0`, and an MCP client can reach `/mcp` on the published port

#### Scenario: Runs unprivileged

- **WHEN** the container starts
- **THEN** the a2web process runs as a non-root user, not uid 0

### Requirement: Browser engines are baked at build time

The image SHALL contain the Chromium binary and system libraries the browser tiers need (`patchright` Chromium with its OS deps; the system Chromium `zendriver` drives), installed during the build. First browser use SHALL NOT trigger a runtime download into the container.

#### Scenario: Browser tier works without a runtime fetch

- **WHEN** a fetch escalates to the browser tier inside the container
- **THEN** it launches the baked Chromium without attempting a network install step

### Requirement: Configuration and secrets come from the environment at runtime

The image SHALL read all configuration from the environment it already supports (`A2WEB_*`, `A2KIT_*`, and provider/secret env such as `ANTHROPIC_API_KEY` / `A2WEB_LLM_*` / `A2WEB_ZYTE_KEY` / `GOOGLE_*`). Secrets SHALL NOT be baked into any image layer. The sqlite cache SHALL live at a path that can be backed by a mounted volume so it survives container restarts.

#### Scenario: Env-supplied secret reaches settings

- **WHEN** the container is started with `A2WEB_ZYTE_KEY` (or another supported var) set in its environment
- **THEN** `AppSettings` resolves it, with no key present in any built image layer

#### Scenario: Cache persists across restarts on a mounted volume

- **WHEN** the sqlite cache path is backed by a mounted volume and the container is restarted
- **THEN** the previously written cache is still present

### Requirement: Liveness probes a transport-native health route on the running server

The image's Docker `HEALTHCHECK` SHALL probe a lightweight HTTP `/health` route served by the **live MCP server itself** (a FastMCP `custom_route`, co-resident with `/mcp` and independent of the `/api` surface, so it is present in MCP-only mode — the FastMCP-idiomatic liveness pattern). The probe reflects whether the long-running `serve` process is up and routing. It SHALL NOT shell out to a fresh `a2web health` (or any other) CLI invocation, which builds a new process and checks sqlite — proving nothing about the running server's liveness.

#### Scenario: Running MCP-only server reports healthy

- **WHEN** the `serve --transport=http` process (MCP-only) is up and bound, and the HEALTHCHECK issues `GET /health`
- **THEN** the server returns HTTP 200 and the container is reported healthy

#### Scenario: Wedged or down server is surfaced

- **WHEN** the `serve` process is not accepting connections (crashed, hung, not yet bound) and the HEALTHCHECK runs
- **THEN** the `GET /health` probe fails to connect and the container is reported unhealthy

#### Scenario: Health route does not depend on the /api surface

- **WHEN** the server is started MCP-only (`--select surface=mcp`, no `/api` sub-app)
- **THEN** `/health` is still served (it rides the MCP app as a `custom_route`, not the FastAPI `/api` sub-app)

#### Scenario: Readiness aggregation stays on the MCP surface

- **WHEN** an operator wants degraded-state (readiness) detail beyond liveness
- **THEN** that is obtained from the `_meta.health` MCP tool over `/mcp`, not from the Docker liveness HEALTHCHECK

### Requirement: Claude SDK is an opt-in build, off by default

The build SHALL default to excluding `claude-agent-sdk` (the `[claude-code]` extra) via an `INSTALL_CLAUDE_CODE` build arg defaulting to false, keeping the published image slim. Setting the arg true SHALL bake the extra in, without requiring a separate Dockerfile.

#### Scenario: Default build is slim

- **WHEN** the image is built with no build args
- **THEN** `claude-agent-sdk` is not installed and the image omits the bundled Claude binary

#### Scenario: Opt-in build includes the SDK

- **WHEN** the image is built with `--build-arg INSTALL_CLAUDE_CODE=true`
- **THEN** the `[claude-code]` extra is installed
