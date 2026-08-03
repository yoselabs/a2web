# container-image Specification

## Purpose
TBD - created by archiving change deployable-container-ci. Update Purpose after archive.
## Requirements
### Requirement: Reproducible slim image with a networked entrypoint

The repository SHALL provide a `Dockerfile` producing an image that installs a2web and its runtime dependencies reproducibly from the lockfile, runs as a **non-root** user, and whose `ENTRYPOINT` starts the HTTP-transport server so the MCP surface is reachable over the network at `/mcp`.

The entrypoint is the `a2web-serve` console script (`a2web.server:serve_http_main`), NOT a `serve` subcommand of the CLI. a2web's Typer CLI is **derived from the registered MCP tools**, so it has exactly the commands those tools produce (`web`, `cookies`) and no framework-level `serve` to invoke.

#### Scenario: Container serves MCP over HTTP

- **WHEN** the image is run with no command override
- **THEN** `a2web-serve` runs `serve_http_main()`, binding the HTTP transport so an MCP client can reach `/mcp` on the published port

#### Scenario: Runs unprivileged

- **WHEN** the container starts
- **THEN** the a2web process runs as a non-root user, not uid 0

### Requirement: Browser engines are baked at build time, under a named build argument

Whether the image carries a browser is decided by ONE build argument, `INSTALL_BROWSER`, declared in the `Dockerfile` and defaulting to `false`. `.github/workflows/release.yml` passes `INSTALL_BROWSER=true`, so **the published image has the browser and a default `docker build` does not.**

When `INSTALL_BROWSER=true`, the image SHALL contain the Chromium binary and system libraries the browser tiers need (`patchright` Chromium with its OS deps; the system Chromium `zendriver` drives), installed during the build. First browser use SHALL NOT then trigger a runtime download into the container.

Stating this conditionally is the correction of a documented contradiction, not pedantry: this spec previously asserted Chromium unconditionally while `CLAUDE.md` asserted the container had no browser at all, and both were describing the same `Dockerfile`. Neither reader could have got the deployment right. The build argument is the single fact; `README.md` and `CLAUDE.md` cite it rather than restating a conclusion.

#### Scenario: Browser tier works without a runtime fetch

- **WHEN** the image was built with `INSTALL_BROWSER=true` (the published shape) and a fetch escalates to the browser tier inside the container
- **THEN** it launches the baked Chromium without attempting a network install step

#### Scenario: A browserless build degrades loudly, never silently

- **WHEN** the image was built without `INSTALL_BROWSER` and a fetch would need the browser rung
- **THEN** the browser tier is unavailable and the fetch returns the ADR-0009 incompleteness envelope — `status: failed`, `retrieval_incomplete: true`, and a critical `try_user_browser` operator hint — never an empty-but-`ok` result

#### Scenario: The build argument cannot drift from what release publishes

- **WHEN** the `Dockerfile`'s `INSTALL_BROWSER` default or `release.yml`'s build-arg value is changed
- **THEN** the guard reading both files fails, so the published shape and the documented shape are corrected together

### Requirement: Configuration and secrets come from the environment at runtime

The image SHALL read all configuration from the environment it already supports (`A2WEB_*` and provider/secret env such as `ANTHROPIC_API_KEY` / `A2WEB_LLM_*` / `A2WEB_ZYTE_KEY` / `A2WEB_GOOGLE_*`). Secrets SHALL NOT be baked into any image layer.

**The `A2WEB_` prefix on the OAuth vars is load-bearing and this spec previously got it wrong.** `AppSettings` uses `env_prefix="A2WEB_"` with `extra="ignore"`, so a bare `GOOGLE_CLIENT_ID` reaches nothing — an operator who set it would have believed the endpoint was authenticated while it served open. a2web now refuses to boot in that state rather than serving. A spec naming `GOOGLE_*` as supported configuration is the inverse of that protection. The sqlite cache SHALL live at a path that can be backed by a mounted volume so it survives container restarts.

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

