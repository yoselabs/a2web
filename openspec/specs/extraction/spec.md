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

### Requirement: Recall-based escalation trigger

After `extract_markdown` returns, `_phase_extract` SHALL decide whether to escalate by a recall signal — whether trafilatura under-extracted relative to the substantive content present in the raw HTML — NOT by an absolute length threshold on `content_md`. A `content_md` that is short because the page is genuinely short (high recall — trafilatura kept most of the page's substantive text) SHALL NOT trigger escalation. A `content_md` that is short because trafilatura discarded a large substantive region (low recall) SHALL trigger escalation. An absolute floor MAY still force escalation on near-empty output.

#### Scenario: Complete short article does not escalate

- **WHEN** trafilatura returns a complete short article and the raw HTML carries little additional substantive content
- **THEN** no escalation is triggered

#### Scenario: Gutted listing escalates

- **WHEN** trafilatura returns a short `content_md` but the raw HTML carries a large repeated record region it discarded
- **THEN** escalation is triggered

#### Scenario: Near-empty output escalates regardless of recall

- **WHEN** `content_md` is near-empty
- **THEN** escalation is triggered regardless of the recall signal

### Requirement: Multi-source extraction escalation ladder

When the recall trigger fires, `_phase_extract` SHALL run an ordered ladder of structured-extraction sources, stopping at the first whose output passes the quality-aware replace check: (1) `json_in_script` payloads (embedded JSON, including JSON-LD); (2) structural record extraction via the `record-extraction` capability. When no source produces a passing result, the cascade SHALL leave `content_md` unchanged and fall through, so the orchestrator's existing browser-tier escalation still applies. Each source attempt SHALL emit `StageStarted` / `StageEnded` LDD events naming the source.

#### Scenario: Embedded JSON is tried first

- **WHEN** the raw HTML carries embedded JSON
- **THEN** the `json_in_script` source is attempted first and, if its output passes the replace check, the ladder stops

#### Scenario: Server-rendered listing reaches record extraction

- **WHEN** the raw HTML is a server-rendered listing with no embedded JSON
- **THEN** the `json_in_script` source yields nothing and the structural record-extraction source runs

#### Scenario: No source passes — clean fall-through

- **WHEN** no ladder source produces a passing result
- **THEN** `content_md` is left unchanged and the cascade falls through to the orchestrator's browser-tier escalation

### Requirement: Quality-aware content replacement

A ladder source's output SHALL replace `content_md` only when it is a dominant substantive result — for record extraction, a record cluster of at least a minimum count where each record carries text and a link. Output SHALL NOT replace `content_md` on length alone: a longer-but-lower-quality candidate (a related-posts widget, a navigation cluster) SHALL NOT win over trafilatura's article output.

#### Scenario: Substantive record cluster replaces gutted output

- **WHEN** a source produces a dominant substantive record cluster larger than trafilatura's output
- **THEN** it replaces `content_md`

#### Scenario: Longer chrome candidate does not replace

- **WHEN** a source produces a longer candidate that is page chrome rather than substantive records
- **THEN** `content_md` is NOT replaced

#### Scenario: A good article is never clobbered

- **WHEN** trafilatura already produced a substantive article and a competing record cluster is detected on the same page
- **THEN** the record cluster does NOT replace the article

### Requirement: JSON-LD ItemList synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `ItemList` payload — an `itemListElement` array of `ListItem` entries — into record rows, each carrying the item name and url. `json_in_script` already detects `ld_json` payloads and `rank_payloads` already prefers `ItemList`; this requirement closes the synthesis gap so a detected `ItemList` becomes usable `content_md`.

#### Scenario: ItemList renders to record rows

- **WHEN** a thin page carries a JSON-LD `ItemList` with a populated `itemListElement` array
- **THEN** `json_to_markdown_rows` renders one row per list item, each with the item name and url

#### Scenario: Empty ItemList yields no rows

- **WHEN** the `ItemList` is empty or malformed
- **THEN** the adapter yields no rows and the ladder continues to the next source

