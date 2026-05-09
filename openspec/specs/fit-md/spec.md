# fit-md Specification

## Purpose
TBD - created by archiving change pr6-fit-md-streaming. Update Purpose after archive.
## Requirements
### Requirement: Pruning filter produces a denser markdown

The system SHALL provide `prune_html(html: str, *, threshold: float = 0.5) -> str` in `src/a2web/extract/pruning_filter.py`. The function SHALL parse the HTML via selectolax, score each block element by text-density and tag-class signals (penalizing `nav`, `aside`, `footer`, `script`, `style`), drop blocks below the threshold, and serialize the survivors to markdown via trafilatura's markdown output. The function SHALL be sync and pure; the orchestrator wraps it in `asyncio.to_thread` at the single chokepoint per the existing extraction discipline.

#### Scenario: fit_md is shorter than content_md on a typical blog

- **WHEN** `prune_html(html=<blog fixture>)` runs and is converted to markdown
- **THEN** `len(fit_md)` is at most 80% of `len(content_md)` for the same fixture, and the output preserves the article's `<h1>` and `<h2>` structure

#### Scenario: Pruning failure falls back gracefully

- **WHEN** the parser raises on malformed HTML (or returns an empty document)
- **THEN** `prune_html` returns the input HTML's text content unchanged or an empty string; the orchestrator sets `fit_md = content_md` and continues

### Requirement: fit_md populated only on successful fetches

The orchestrator SHALL populate `FetchResponse.fit_md` and `FetchResponse.tokens` only when the gate verdict is `Verdict.ok`. Failed or blocked responses SHALL leave `fit_md = None` and `tokens = None`.

#### Scenario: Length-floor failure leaves fit_md None

- **WHEN** the gate emits `Verdict.length_floor` (extracted markdown <500 chars)
- **THEN** the returned `FetchResponse.fit_md is None` and `FetchResponse.tokens is None`

#### Scenario: Successful fetch populates token counts

- **WHEN** a successful fetch completes against the blog fixture
- **THEN** `FetchResponse.tokens.full == len(content_md)` and `FetchResponse.tokens.fit == len(fit_md)`

### Requirement: Pre-rendered handler results skip pruning

When `tier_extras["pre_rendered"]` is set (handlers like Reddit/HN), the orchestrator SHALL set `fit_md = content_md` and SHALL NOT invoke `prune_html`. Handler-rendered markdown is already minimal (the comment tree is the data; pruning would discard signal).

#### Scenario: Reddit handler keeps fit_md == content_md

- **WHEN** a fetch routes to the Reddit handler and produces pre-rendered markdown
- **THEN** `FetchResponse.fit_md == FetchResponse.content_md`

