## REMOVED Requirements

### Requirement: htmldate publication and update dates

**Reason:** Replaced by trafilatura's `bare_extraction(with_metadata=True)`, which returns publish + last-modified dates as part of its metadata block. The standalone `htmldate` dependency and the `extract/htmldate_ext.py` module are dropped.

**Migration:** Delete `src/a2web/extract/htmldate_ext.py`. The orchestrator no longer calls `find_published(...)` / `find_updated(...)` separately — the date arrives in the trafilatura result. Remove `htmldate` from `pyproject.toml`.

### Requirement: OpenGraph + Twitter + JSON-LD metadata

**Reason:** Trafilatura's metadata extraction covers OG / Twitter / JSON-LD via its internal `metadata` module. The custom `parse_metadata` in `src/a2web/extract/metadata.py` duplicates work trafilatura already does.

**Migration:** Delete `src/a2web/extract/metadata.py`. The orchestrator consumes `Document.metadata` (or equivalent field on trafilatura's result) and surfaces it on `FetchResponse.meta` with the same key set as v0.1.0 (`og.type`, `og.image`, `twitter.card`, `jsonld[0].author`, etc.). Map trafilatura's metadata field names to the v0.1.0 key set in the orchestrator (or in a tiny `_to_v01_meta(...)` translator) so the wire surface is unchanged.

## MODIFIED Requirements

### Requirement: Trafilatura markdown extraction

The system SHALL provide `async extract_markdown(html: str, url: str) -> ExtractResult` in `src/a2web/extract/trafilatura_ext.py`. The implementation SHALL call trafilatura's `bare_extraction(html, url=url, with_metadata=True, output_format="markdown")` (or the current API equivalent at adoption time) inside `asyncio.to_thread`. The single call SHALL produce:

- `content_md: str` — extracted markdown body
- `title: str | None` — from metadata
- `byline: str | None` — author / byline from metadata
- `published: date | None` — publication date from metadata
- `headings: list[Heading]` — derived from the markdown body or trafilatura's structured output
- `links: list[Link]` — derived from the markdown body
- `meta: dict[str, str]` — flattened OG / Twitter / JSON-LD metadata, with the v0.1.0 key set

`ExtractResult` SHALL be a `@dataclass(slots=True)` at module scope. The chokepoint to sync trafilatura calls SHALL remain in `_extract_sync(...)` per the existing ASYNC lint contract.

#### Scenario: Single call returns body + metadata + date

- **WHEN** `await extract_markdown(html, url)` runs against a fixture with `<meta property="article:published_time">` and an OG image tag
- **THEN** the result has non-empty `content_md`, populated `title`, `published` matching the fixture date, and `meta["og.image"]` matching the OG image URL

#### Scenario: ASYNC chokepoint preserved

- **WHEN** ruff scans `src/a2web/extract/trafilatura_ext.py`
- **THEN** ASYNC100/210/230 emits zero diagnostics

#### Scenario: Missing metadata yields Nones, not exceptions

- **WHEN** `extract_markdown(html, url)` runs against a fixture with no metadata
- **THEN** `result.title is None`, `result.published is None`, and `result.meta == {}`; no exception is raised

## ADDED Requirements

### Requirement: htmldate dependency removed

`pyproject.toml` SHALL NOT list `htmldate` as a dependency after Phase B. Static analysis SHALL confirm no module in `src/a2web/` imports `htmldate`.

#### Scenario: htmldate import absent

- **WHEN** `grep -r "import htmldate" src/` runs after Phase B
- **THEN** zero matches are returned
