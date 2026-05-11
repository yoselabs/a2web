## MODIFIED Requirements

### Requirement: App composition uses imperative singleton + lifecycle hooks

The system SHALL compose `app` in `src/a2web/server.py` using a2kit v0.26 imperative APIs:

```
app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())
app.singleton(AppState, factory=build_state)

@app.on_startup
async def _open(state: AppState) -> None: ...

@app.on_shutdown
async def _close(state: AppState) -> None: ...

@app.health_check
async def _sqlite(state: AppState) -> a2kit.HealthResult: ...

app.ldd.add_sink(otel_sink)
```

The composition SHALL NOT use the fluent multi-line chain form for non-trivial registration; the imperative form is canonical. `connections_cli(...)` SHALL NOT appear (a2web has no connection concept).

#### Scenario: Server module composes the app on import

- **WHEN** `from a2web.server import app` is executed
- **THEN** the App has one router, one singleton (`AppState`), startup/shutdown hooks registered, one health check, and the OTel sink registered on `app.ldd`

#### Scenario: health tool advertised

- **WHEN** an operator runs `a2web health` from the CLI
- **THEN** the command exits 0 when sqlite is open AND non-zero when sqlite is not open or any registered health check returns `fail`

### Requirement: fetch tool carries MCP tool annotations and Param descriptions

`WebRouter.fetch` SHALL be decorated with `@a2kit.read(Surface.ALL, idempotent=True, open_world=True, title="Fetch Web Page")`. The `url` parameter SHALL be annotated `Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")]`. The tool docstring SHALL follow the documented contract — a short first-line summary followed by a multi-paragraph body explaining the cascade, escalation behavior, and return shape; markdown is intact on MCP and stripped on CLI by a2kit.

#### Scenario: MCP tool annotations reach the client

- **WHEN** an MCP client requests the `fetch` tool descriptor
- **THEN** the descriptor carries `openWorldHint=true`, `idempotentHint=true`, `readOnlyHint=true`, `destructiveHint=false`, and `title="Fetch Web Page"`

#### Scenario: Param description reaches input schema

- **WHEN** an MCP client requests the `fetch` tool's input schema
- **THEN** the `url` parameter has a `description` field matching the `a2kit.Param` value AND the schema contains no `state` or `ctx` parameter

#### Scenario: Docstring multi-paragraph body reaches MCP description

- **WHEN** an MCP client requests the `fetch` tool descriptor
- **THEN** the tool `description` is the full multi-paragraph docstring body (markdown intact), not just the first line

#### Scenario: CLI help shows stripped description

- **WHEN** a CLI user runs `a2web web fetch --help`
- **THEN** the help text shows the first-line summary as the brief and renders any longer body with markdown formatting stripped to plain text

## REMOVED Requirements

### Requirement: Server composition entrypoint

**Reason:** Replaced by the imperative composition described above. The `register_state` helper is deleted (a2kit v0.26 `app.singleton` covers it).

**Migration:** See the imperative composition pattern in the requirement above; `register_state(app)` calls are replaced by `app.singleton(AppState, factory=build_state)` plus the lifecycle hooks.
