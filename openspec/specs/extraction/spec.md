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

### Requirement: Multi-source extraction escalation ladder

After `extract_markdown` returns, `_phase_extract` SHALL run an ordered ladder of structured-extraction sources **unconditionally** — there is no recall trigger gating entry to the ladder. Each rung self-gates: it produces output only when its own preconditions hold — `json_in_script` only when embedded JSON is present; structural record extraction only when a record region clears the `record-extraction` detection guards. The ladder runs in order: (1) `json_in_script` payloads (embedded JSON, including JSON-LD); (2) structural record extraction via the `record-extraction` capability. The ladder stops at the first rung whose output passes the quality-aware replace check. When no rung produces a passing result, the cascade SHALL leave `content_md` unchanged and fall through, so the orchestrator's existing browser-tier escalation still applies. Each rung SHALL emit `StageStarted` / `StageEnded` LDD events naming the source.

#### Scenario: Ladder runs without a trigger

- **WHEN** `extract_markdown` returns for any page
- **THEN** the escalation ladder runs, and each rung self-gates on its own preconditions

#### Scenario: Embedded JSON is tried first

- **WHEN** the raw HTML carries embedded JSON
- **THEN** the `json_in_script` source is attempted first and, if its output passes the replace check, the ladder stops

#### Scenario: Server-rendered listing reaches record extraction

- **WHEN** the raw HTML is a server-rendered listing with no embedded JSON
- **THEN** the `json_in_script` source yields nothing and the structural record-extraction source runs

#### Scenario: Article reaches the record rung and it self-gates

- **WHEN** the page is a genuine article
- **THEN** the structural record-extraction rung runs, returns no record set, and `content_md` is left unchanged

#### Scenario: No source passes — clean fall-through

- **WHEN** no ladder rung produces a passing result
- **THEN** `content_md` is left unchanged and the cascade falls through to the orchestrator's browser-tier escalation

### Requirement: Quality-aware content replacement

A ladder source's output SHALL replace `content_md` only when it is a higher-quality result than trafilatura's output. For structural record extraction the replace decision SHALL be **depth-aware**: a **threaded** record set (maximum nesting depth > 0) SHALL replace `content_md` whenever the detector produced one — trafilatura cannot represent threading, so rendered length is not a quality proxy for it; a **flat** record set (depth 0) SHALL replace `content_md` only when its rendered length exceeds trafilatura's output. A good article SHALL NOT be clobbered: an article yields no record set because the `record-extraction` detection guards reject it, so the replace check is never reached. A `json_in_script` source SHALL replace `content_md` when its synthetic output exceeds trafilatura's output in length.

#### Scenario: Threaded record set replaces a flattened wall

- **WHEN** structural record extraction produces a threaded (depth > 0) record set on a page trafilatura flattened into an undifferentiated wall of text
- **THEN** the threaded render replaces `content_md` even if it is shorter than trafilatura's output

#### Scenario: Flat catalog replaces on length

- **WHEN** structural record extraction produces a flat (depth 0) record set whose rendered length exceeds trafilatura's output
- **THEN** it replaces `content_md`

#### Scenario: A good article is never clobbered

- **WHEN** the page is an article
- **THEN** the record-extraction guards reject it, no record set is produced, and `content_md` keeps trafilatura's output

### Requirement: JSON-LD ItemList synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `ItemList` payload — an `itemListElement` array of `ListItem` entries — into record rows, each carrying the item name and url. `json_in_script` already detects `ld_json` payloads and `rank_payloads` already prefers `ItemList`; this requirement closes the synthesis gap so a detected `ItemList` becomes usable `content_md`.

#### Scenario: ItemList renders to record rows

- **WHEN** a thin page carries a JSON-LD `ItemList` with a populated `itemListElement` array
- **THEN** `json_to_markdown_rows` renders one row per list item, each with the item name and url

#### Scenario: Empty ItemList yields no rows

- **WHEN** the `ItemList` is empty or malformed
- **THEN** the adapter yields no rows and the ladder continues to the next source

