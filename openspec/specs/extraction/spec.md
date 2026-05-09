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

