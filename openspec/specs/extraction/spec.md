# extraction Specification

## Purpose
TBD - created by archiving change pr3-raw-tier. Update Purpose after archive.
## Requirements
### Requirement: Trafilatura markdown extraction

The system SHALL provide `async extract_markdown(html: str, url: str) -> ExtractResult` in `src/a2web/extract/trafilatura_ext.py`. The implementation SHALL call trafilatura's `extract` with markdown output and run synchronously inside `asyncio.to_thread`. `ExtractResult` SHALL be a `@dataclass(slots=True)` carrying `content_md: str`, `title: str | None`, `byline: str | None`, `headings: list[Heading]`, `links: list[Link]`, `score: float | None`. Trafilatura blocking calls SHALL NOT appear outside this module's `_extract_sync` helper.

#### Scenario: Sync chokepoint per ASYNC lint

- **WHEN** ruff scans `src/a2web/extract/trafilatura_ext.py`
- **THEN** ASYNC100/210/230 emits zero diagnostics

#### Scenario: Markdown output for a well-formed article fixture

- **WHEN** `extract_markdown(html=<blog post fixture>, url=<fixture url>)` is awaited
- **THEN** the result has non-empty `content_md`, a non-empty `title`, and at least one `Heading`

### Requirement: htmldate publication and update dates

The system SHALL provide `async find_published(html: str, url: str) -> date | None` and `async find_updated(html: str, url: str) -> date | None` in `src/a2web/extract/htmldate_ext.py`. Both SHALL wrap htmldate sync calls via `asyncio.to_thread`. Returning `None` (no detectable date) SHALL be a normal outcome, never an exception.

#### Scenario: Date present

- **WHEN** `find_published` is awaited on a fixture with `<meta property="article:published_time">`
- **THEN** the returned value is a `datetime.date` matching the fixture

#### Scenario: Date absent

- **WHEN** `find_published` is awaited on a fixture with no date markers
- **THEN** the returned value is `None`

### Requirement: OpenGraph + Twitter + JSON-LD metadata

The system SHALL provide `parse_metadata(html: str) -> dict[str, str]` in `src/a2web/extract/metadata.py` as a pure synchronous function. It SHALL extract `og:*`, `twitter:*` meta tags and the first JSON-LD block (`<script type="application/ld+json">`), flattened with dot-keys: `og.type`, `og.image`, `twitter.card`, `jsonld[0].author`, `jsonld[0].datePublished`, etc. Missing fields SHALL be omitted from the dict (no `None` values).

#### Scenario: OG type and image extraction

- **WHEN** `parse_metadata(html)` is called on a fixture with `<meta property="og:type" content="article">` and `<meta property="og:image" content="https://x/y.jpg">`
- **THEN** the returned dict contains `og.type == "article"` and `og.image == "https://x/y.jpg"`

#### Scenario: JSON-LD author and date

- **WHEN** `parse_metadata(html)` is called on a fixture with a JSON-LD `Article` carrying `author` and `datePublished`
- **THEN** the returned dict contains `jsonld[0].author` and `jsonld[0].datePublished`

### Requirement: JSON-in-script extraction runs when trafilatura is thin

After `extract_markdown` returns, the orchestrator's `_phase_extract` SHALL check `len(result.content_md) < 2_048` OR `count_sentences(result.content_md) < 3`. If either holds, the orchestrator SHALL call the `json_in_script` extractor on the original HTML, rank the returned payloads via `rank_payloads`, and convert the top payload to a synthetic markdown table via a domain-side adapter `json_to_markdown_rows`. The synthetic markdown SHALL replace `result.content_md` ONLY IF the synthetic length exceeds the original by ≥2× (otherwise the original wins — JSON path didn't help). The replacement SHALL emit `StageStarted("json_synth")` / `StageEnded("json_synth", verdict="replaced"|"kept_original")` LDD events.

#### Scenario: Trendyol thin trafilatura output replaced by Next.js product table

- **WHEN** `_phase_extract` runs on the Trendyol search HTML, trafilatura returns 642 chars of nav menu, `json_in_script` finds `__NEXT_DATA__` with `pageProps.products`, and `json_to_markdown_rows` synthesizes a 12 KB product table
- **THEN** `result.content_md` is the synthetic table; LDD records `json_synth` with `verdict="replaced"`

#### Scenario: SSR article keeps trafilatura output

- **WHEN** trafilatura returns 8 KB of clean article markdown
- **THEN** the JSON path does not run (above the 2 KB / 3-sentence threshold); no `json_synth` event is emitted

#### Scenario: JSON path runs but doesn't improve

- **WHEN** trafilatura returns 1 KB and `json_in_script` finds payloads but `json_to_markdown_rows` produces only 1.5 KB (below the 2× threshold)
- **THEN** the original trafilatura output is kept; LDD records `json_synth` with `verdict="kept_original"`

### Requirement: max_content_chars override flows from CLI / MCP to the extractor

The `Extractor.__init__` already accepts `max_content_chars: int = 100_000`. The orchestrator SHALL accept an optional `max_content_chars: int | None` parameter on `fetch()` that overrides the default for a single call. The CLI SHALL expose this as `--max-content-chars INT` on both `ask` and `fetch_raw` tools (also surfaced as an Annotated kwarg on the MCP tools). When the override is `None` or absent, the existing 100,000-char default applies. When set, the override SHALL be plumbed through `FetchContext.max_content_chars` to `LlmExtractorResource.extract()` to `Extractor.extract()`'s truncation step.

#### Scenario: CLI flag caps content before extraction

- **WHEN** a caller invokes `a2web web ask --url <yandex-market-url> --question <q> --max-content-chars 50000` against a page whose raw markdown is 345 KB
- **THEN** the prompt sent to the extractor model contains at most 50,000 chars of content (plus the truncation marker), and the `tokens.full` field on the response reflects the capped count

#### Scenario: Default behavior preserved when flag absent

- **WHEN** a caller invokes `a2web web ask --url <url> --question <q>` without the new flag
- **THEN** the existing 100,000-char default applies; no behavior change from the pre-fix release

#### Scenario: MCP kwarg matches CLI flag

- **WHEN** an MCP client calls the `fetch` tool with `max_content_chars=50000`
- **THEN** the same cap applies; the MCP tool schema documents the kwarg via `Annotated[int | None, pydantic.Field(description=...)]`

