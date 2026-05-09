## MODIFIED Requirements

### Requirement: Public fetch tool envelope

The system SHALL expose a single `fetch` tool whose return type is a module-scope pydantic model named `FetchResponse`. The tool SHALL NOT return `str`, `dict`, or any nested-class type. The envelope SHALL include all fields specified in `v0.1-response-format.md` §2:

- **Top scalars**: `url: str`, `status: FetchStatus`, `tier: str`, `confidence: Confidence`, `title: str | None`, `byline: str | None`, `published: date | None`, `started_at: datetime`, `total_ms: int`, `tokens: TokenCounts | None`, `cache: CacheState`.
- **Sections**: `narrative: str`, `diagnostics: list[Diagnostic]`, `meta: dict[str, str]`, `links: list[Link]`, `headings: list[Heading]`, `content_md: str`, `fit_md: str | None`, `operator_hints: list[OperatorHint]`.

The tool function signature SHALL declare `state: AppState` as a DI kwarg. The `state` kwarg SHALL NOT appear in the MCP wire schema. The tool SHALL invoke the orchestrator at `a2web.fetcher.fetch(url, state=state)` and return its result.

After PR4, every successful or failed fetch SHALL produce exactly one `LogRecord` entry on disk via `state.log_writer.write_record(...)` — unless `state.settings.log_enabled is False`, in which case the writer is a no-op. A log write failure SHALL NOT cause the fetch to fail; it SHALL append an `OperatorHint(code="log_write_failed", ...)` to the response and continue.

#### Scenario: Successful fetch produces one log record

- **WHEN** `fetch` is invoked against a mock tier returning a usable body and `log_enabled=True`
- **THEN** the configured log file gains exactly one new line, parseable as JSON, with `status="ok"`, `tier`, `verdict="ok"`, `total_ms`, and the fetched `url`

#### Scenario: Failed fetch also produces a log record

- **WHEN** `fetch` is invoked against a mock tier returning a block-page body
- **THEN** the configured log file gains exactly one new line with `status="failed"` and `verdict="block_page_detected"`

#### Scenario: Disabled log writer produces no file output

- **WHEN** `fetch` is invoked with `state.settings.log_enabled=False`
- **THEN** no files are created under the log directory

#### Scenario: Log write failure surfaces as operator hint

- **WHEN** the writer raises during a fetch (e.g. unwritable directory)
- **THEN** the `FetchResponse.operator_hints` includes one entry with `code == "log_write_failed"` and the response otherwise reflects the underlying fetch outcome (not the log failure)
