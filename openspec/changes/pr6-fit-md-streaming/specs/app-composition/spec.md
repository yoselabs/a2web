## MODIFIED Requirements

### Requirement: Public fetch tool envelope

The system SHALL expose a single `fetch` tool whose return type is a module-scope pydantic model named `FetchResponse`. The tool SHALL NOT return `str`, `dict`, or any nested-class type. The envelope SHALL include all fields specified in `v0.1-response-format.md` §2.

The tool function signature SHALL declare `state: AppState` and `ctx: a2kit.ToolContext` as DI kwargs. Neither SHALL appear in the MCP wire schema. The tool SHALL build an `EventBus` per call, attach the MCP progress sink, invoke the orchestrator with the bus, and return the populated `FetchResponse`. Successful fetches SHALL populate `fit_md` and `tokens`.

After PR4, every successful or failed fetch SHALL produce exactly one `LogRecord` entry on disk via `state.log_writer.write_record(...)`. Log write failures append `OperatorHint(code="log_write_failed", ...)`.

#### Scenario: state and ctx kwargs are hidden from the wire schema

- **WHEN** an MCP client requests the `fetch` tool's input schema
- **THEN** the schema's required/optional parameters list `url` only — neither `state` nor `ctx` appears

#### Scenario: Successful fetch populates fit_md and tokens

- **WHEN** a successful fetch returns a `FetchResponse` against the blog fixture
- **THEN** `response.fit_md is not None`, `response.tokens.full == len(response.content_md)`, `response.tokens.fit == len(response.fit_md)`

#### Scenario: Failed fetch leaves fit_md None

- **WHEN** a fetch fails the gate
- **THEN** `response.fit_md is None` and `response.tokens is None`

#### Scenario: MCP progress notifications fire per phase

- **WHEN** the `fetch` tool is invoked through the App pipeline with a mock `ToolContext`
- **THEN** the context records at least one `ctx.event` call per tier/stage boundary and `ctx.report_progress` calls only on End events
