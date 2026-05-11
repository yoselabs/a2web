# tier-pipeline (delta)

## ADDED Requirements

### Requirement: `fetch` tool accepts optional `ask` parameter

The `WebRouter.fetch` tool SHALL accept an optional `ask: str | None = None` parameter. When `ask` is non-None, the orchestrator SHALL invoke the `llm` module after the existing extract phase to produce an answer, and SHALL populate `FetchResponse.extracted_answer` with the answer text and `FetchResponse.extraction` with `ExtractionMeta` (model, tokens, cost, cache_hit).

When `ask` is None (the default), the existing pipeline SHALL run unchanged and `extracted_answer` SHALL be `None`. No LLM provider is invoked, no anthropic SDK is imported, and the response is identical to v0.3 behavior.

#### Scenario: ask= unset produces no extraction

- **WHEN** `fetch(url="https://example.com")` is invoked with no `ask`
- **THEN** `FetchResponse.extracted_answer is None`
- **AND** `FetchResponse.extraction is None`
- **AND** no anthropic API call is made

#### Scenario: ask= triggers extraction

- **GIVEN** `[llm]` extra is installed and `ANTHROPIC_API_KEY` is set
- **WHEN** `fetch(url="https://en.wikipedia.org/wiki/Rust_(programming_language)", ask="Who designed Rust?")` is invoked
- **THEN** `FetchResponse.extracted_answer` is a non-empty string containing "Graydon Hoare"
- **AND** `FetchResponse.extraction.model == "claude-haiku-4-5-20251001"` (or the configured override)
- **AND** `FetchResponse.extraction.cost_usd > 0` on first call

### Requirement: `ask=` without LLM available degrades gracefully

When `ask` is set but `[llm]` is not installed OR `state.llm_client` is None (no API key configured), the fetch SHALL still complete with `status=ok` (assuming the underlying fetch succeeded). The response SHALL include `extracted_answer=None` and an `operator_hints` entry with `code="llm_unavailable"` and a message including the install/config hint.

#### Scenario: ask= with no key produces an operator hint, not a failure

- **GIVEN** `ANTHROPIC_API_KEY` is not set (or `[llm]` extra not installed)
- **WHEN** `fetch(url=<valid-url>, ask="...")` is invoked
- **THEN** the fetch returns with `status=ok` and the regular content envelope populated
- **AND** `extracted_answer is None`
- **AND** `operator_hints` contains an entry with `code="llm_unavailable"`

### Requirement: Extraction content cap

The content passed to the extractor SHALL be truncated to `settings.extraction_max_chars` (default 100,000, matching WebFetch's `BD_` constant). Truncation SHALL append a clearly delineated marker (e.g. `[Content truncated to 100000 chars]`) so the model knows it received a prefix.

#### Scenario: long content is truncated before extraction

- **WHEN** the extracted `content_md` is 250,000 characters
- **THEN** the string actually passed to the extractor is 100,000 chars plus a one-line truncation marker
- **AND** the answer is generated from the truncated prefix
