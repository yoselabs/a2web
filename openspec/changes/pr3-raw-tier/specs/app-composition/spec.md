## MODIFIED Requirements

### Requirement: Public fetch tool envelope

The system SHALL expose a single `fetch` tool whose return type is a module-scope pydantic model named `FetchResponse`. The tool SHALL NOT return `str`, `dict`, or any nested-class type. The envelope SHALL include all fields specified in `v0.1-response-format.md` §2:

- **Top scalars**: `url: str`, `status: FetchStatus`, `tier: str`, `confidence: Confidence`, `title: str | None`, `byline: str | None`, `published: date | None`, `started_at: datetime`, `total_ms: int`, `tokens: TokenCounts | None`, `cache: CacheState`.
- **Sections**: `narrative: str`, `diagnostics: list[Diagnostic]`, `meta: dict[str, str]`, `links: list[Link]`, `headings: list[Heading]`, `content_md: str`, `fit_md: str | None`, `operator_hints: list[OperatorHint]`.

The tool function signature SHALL declare `state: AppState` as a DI kwarg. The `state` kwarg SHALL NOT appear in the MCP wire schema. The tool SHALL invoke the orchestrator at `a2web.fetcher.fetch(url, state=state)` and return its result. The placeholder narrative ("PR2 stub …") SHALL be removed; the narrative SHALL describe what the orchestrator did (which tier produced content, cache state, total duration formatted via `fmt_dur`).

#### Scenario: Real content_md on a generic blog URL

- **WHEN** the `fetch` tool is invoked with the canned blog-post HTML fixture (or a network-marked test URL)
- **THEN** the returned `FetchResponse.content_md` is non-empty markdown, `tier == "raw"`, `status == FetchStatus.ok`, `cache == "miss"`, and `total_ms > 0`

#### Scenario: Cache hit on second call

- **WHEN** the same URL is fetched twice in succession (with the cache enabled and the URL not in `live_only_hosts`)
- **THEN** the second response has `cache == "hit"` and `total_ms < 50` (no network)

#### Scenario: Failed fetch on block page

- **WHEN** the fetch produces a body matching one of the block-page regexes
- **THEN** `status == FetchStatus.failed`, the diagnostics list contains a row with `verdict == Verdict.block_page_detected`, and no cache row exists for the URL

#### Scenario: state kwarg is hidden from the wire schema

- **WHEN** an MCP client requests the `fetch` tool's input schema
- **THEN** the schema's required/optional parameters list `url` only and SHALL NOT include `state`
