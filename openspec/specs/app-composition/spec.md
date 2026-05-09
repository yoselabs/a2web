# app-composition Specification

## Purpose
TBD - created by archiving change pr1-app-composition. Update Purpose after archive.
## Requirements
### Requirement: Public fetch tool envelope

The system SHALL expose a single `fetch` tool whose return type is a module-scope pydantic model named `FetchResponse`. The tool SHALL NOT return `str`, `dict`, or any nested-class type. The envelope SHALL include all fields specified in `v0.1-response-format.md` §2:

- **Top scalars**: `url: str`, `status: FetchStatus`, `tier: str`, `confidence: Confidence`, `title: str | None`, `byline: str | None`, `published: date | None`, `started_at: datetime`, `total_ms: int`, `tokens: TokenCounts | None`, `cache: CacheState`.
- **Sections**: `narrative: str`, `diagnostics: list[Diagnostic]`, `meta: dict[str, str]`, `links: list[Link]`, `headings: list[Heading]`, `content_md: str`, `fit_md: str | None`, `operator_hints: list[OperatorHint]`.

#### Scenario: Tool returns a typed envelope

- **WHEN** the `fetch` tool is invoked with any URL in PR1
- **THEN** the return value is an instance of `FetchResponse` with all required fields populated (placeholder values acceptable in PR1)

#### Scenario: All return types at module scope

- **WHEN** a static analysis pass walks `src/a2web/models.py`
- **THEN** `FetchResponse`, `Diagnostic`, `Heading`, `Link`, `OperatorHint`, `TokenCounts`, `Verdict`, `FetchStatus`, `Confidence`, `CacheState` are defined at module scope and importable as `from a2web.models import ...`

### Requirement: Closed-enum diagnostic verdicts

The system SHALL define `Verdict` as a closed `StrEnum` with members `ok`, `paywall`, `block_page_detected`, `anti_bot`, `length_floor`, `content_type_mismatch`, `connection_error`, `timeout`, `not_found`, `rate_limited`, `proxy_unavailable`, `other`. The `Diagnostic` model SHALL carry the verdict plus an optional `subsystem: str | None` for sub-classification (e.g., `cloudflare`, `datadome`, `anubis`).

#### Scenario: Verdict enum is closed

- **WHEN** code attempts to construct a `Diagnostic` with a verdict outside the defined set
- **THEN** pydantic raises a validation error at construction time

### Requirement: Closed-enum status, confidence, and cache state

The system SHALL define `FetchStatus` as a closed `StrEnum` (`ok`, `failed`, `partial`), `Confidence` as `(high, medium, low)`, and `CacheState` as `(hit, miss, bypass)`.

#### Scenario: Each enum is closed at construction

- **WHEN** code attempts to construct a `FetchResponse` with an out-of-set status, confidence, or cache value
- **THEN** pydantic raises a validation error

### Requirement: Router registration under `web`

The system SHALL register the `fetch` tool inside a router class named `WebRouter` so the CLI surface is `a2web web fetch ...` and the MCP tool name remains `fetch`.

#### Scenario: CLI verb grouping

- **WHEN** the user runs `a2web --help`
- **THEN** the output shows a `web` subcommand group, and `a2web web --help` lists `fetch` as a tool

#### Scenario: MCP tool name is unprefixed

- **WHEN** an MCP client lists tools from `a2web serve`
- **THEN** the tool appears as `fetch` (not `web_fetch` or `web.fetch`)

### Requirement: Server composition entrypoint

The system SHALL expose `a2web.server.main()` as the single entrypoint registered to `[project.scripts] a2web`. `main()` SHALL build an `a2kit.App` and attach `WebRouter`, then invoke `a2kit.run(app)`. The composition SHALL NOT register a connections CLI.

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
- **THEN** the command exits 0 and prints a `FetchResponse` (JSON, since a2kit v0.23 routes single `BaseModel` returns to JSON) with `tier="stub"`, `status="ok"`, and a non-null `started_at`

### Requirement: Configuration via single YAML file plus env vars

The system SHALL load configuration from `AppSettings` (pydantic-settings). The settings model SHALL read, in precedence order: (1) `A2WEB_*` env vars, (2) the YAML file at `$A2WEB_CONFIG` if set, (3) `~/.a2web/config.yaml` if it exists, (4) hard-coded defaults. The fetch tool MUST be callable with no config file present.

The YAML schema SHALL include at minimum: `default_ua: str`, `stealth: bool`, `proxies: dict[str, ProxyEntry]`, `routes: list[RouteRule]`, `cache_ttl_static_h: int`, `cache_ttl_article_h: int`, `cache_ttl_live_m: int`, `log_retention_days: int`, `diagnostics_default: "off" | "brief" | "full"`, `live_only_hosts: list[str]`. The `jina_key` field SHALL be sourced from `A2WEB_JINA_KEY` only and never persisted to the YAML by the tool.

The system SHALL NOT include Firecrawl or Bright Data API key fields in v0.1.

#### Scenario: Zero-config startup

- **WHEN** no config file exists at `~/.a2web/config.yaml` and no `A2WEB_*` env vars are set
- **THEN** `AppSettings()` constructs successfully with defaults and `a2web web fetch --url=...` exits 0

#### Scenario: YAML config overrides defaults

- **WHEN** a YAML file at `$A2WEB_CONFIG` sets `stealth: true`
- **THEN** `AppSettings().stealth` is `True`

#### Scenario: Env var overrides YAML

- **WHEN** the YAML sets `stealth: false` and `A2WEB_STEALTH=true` is exported
- **THEN** `AppSettings().stealth` is `True`

#### Scenario: Jina key is env-only

- **WHEN** the YAML contains a `jina_key` field
- **THEN** that field is ignored; `AppSettings().jina_key` resolves only from `A2WEB_JINA_KEY` (empty string when unset)

