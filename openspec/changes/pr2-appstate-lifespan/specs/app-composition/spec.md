## MODIFIED Requirements

### Requirement: Public fetch tool envelope

The system SHALL expose a single `fetch` tool whose return type is a module-scope pydantic model named `FetchResponse`. The tool SHALL NOT return `str`, `dict`, or any nested-class type. The envelope SHALL include all fields specified in `v0.1-response-format.md` §2:

- **Top scalars**: `url: str`, `status: FetchStatus`, `tier: str`, `confidence: Confidence`, `title: str | None`, `byline: str | None`, `published: date | None`, `started_at: datetime`, `total_ms: int`, `tokens: TokenCounts | None`, `cache: CacheState`.
- **Sections**: `narrative: str`, `diagnostics: list[Diagnostic]`, `meta: dict[str, str]`, `links: list[Link]`, `headings: list[Heading]`, `content_md: str`, `fit_md: str | None`, `operator_hints: list[OperatorHint]`.

The tool function signature SHALL declare `state: AppState` as a DI kwarg. The `state` kwarg SHALL NOT appear in the MCP wire schema (it is resolved via the a2kit container, not supplied by the caller).

#### Scenario: Tool returns a typed envelope

- **WHEN** the `fetch` tool is invoked with any URL in PR2
- **THEN** the return value is an instance of `FetchResponse` with all required fields populated (placeholder values acceptable in PR2)

#### Scenario: All return types at module scope

- **WHEN** a static analysis pass walks `src/a2web/models.py`
- **THEN** `FetchResponse`, `Diagnostic`, `Heading`, `Link`, `OperatorHint`, `TokenCounts`, `Verdict`, `FetchStatus`, `Confidence`, `CacheState` are defined at module scope and importable as `from a2web.models import ...`

#### Scenario: state kwarg is hidden from the wire schema

- **WHEN** an MCP client requests the `fetch` tool's input schema
- **THEN** the schema's required/optional parameters list `url` only and SHALL NOT include `state`

### Requirement: Server composition entrypoint

The system SHALL expose `a2web.server.main()` as the single entrypoint registered to `[project.scripts] a2web`. `main()` SHALL build an `a2kit.App`, attach `WebRouter`, register `AppState` via `register_state(app)`, then invoke `a2kit.run(app)`. The composition SHALL NOT register a connections CLI.

#### Scenario: CLI help is reachable

- **WHEN** the user runs `a2web --help`
- **THEN** the command exits 0 and prints help including `web` and `serve` subcommands

#### Scenario: No connections subcommand

- **WHEN** the user runs `a2web --help`
- **THEN** the output does NOT include a `connections` subcommand group

#### Scenario: Stdio MCP server starts

- **WHEN** the user runs `a2web serve --transport=stdio` and sends an MCP `initialize` message
- **THEN** the server responds with capability metadata including the `fetch` tool

#### Scenario: Stub fetch invocation succeeds

- **WHEN** the user runs `a2web web fetch --url=https://example.com`
- **THEN** the command exits 0, prints a `FetchResponse` (default JSON format) with `tier="stub"`, `status="ok"`, a non-null `started_at`, and a narrative that mentions `diagnostics_default`

#### Scenario: AppState provider is registered

- **WHEN** `from a2web.server import app` is executed
- **THEN** `app.has_provider(AppState)` returns `True`
