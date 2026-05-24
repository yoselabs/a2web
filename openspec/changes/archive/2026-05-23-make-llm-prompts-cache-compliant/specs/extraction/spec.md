## ADDED Requirements

### Requirement: Cacheable prompt template with byte-stable prefix

The system SHALL provide a `PromptTemplate` named `EXTRACT_CACHEABLE_V1` in `src/a2web/packages/llm_extract/prompts.py` whose `render(content, ask)` method returns a `PromptParts(system, cache_prefix, tail)` value where, for any fixed `content`, `system` and `cache_prefix` are byte-identical across all values of `ask`. The `tail` SHALL carry the variable per-call portion (the user question). The `cache_prefix` SHALL include the page content. The `system` SHALL include the static response-mode rules.

#### Scenario: Same content, different asks — prefix stable

- **WHEN** `EXTRACT_CACHEABLE_V1.render(content=<page>, ask="Q1")` and `EXTRACT_CACHEABLE_V1.render(content=<page>, ask="Q2")` are computed
- **THEN** the two results share identical `system` and `cache_prefix` strings byte-for-byte, and the two `tail` strings differ

#### Scenario: Different content — prefix differs

- **WHEN** `EXTRACT_CACHEABLE_V1.render(content=<page A>, ask="Q")` and `EXTRACT_CACHEABLE_V1.render(content=<page B>, ask="Q")` are computed
- **THEN** the two `cache_prefix` strings differ (page content is part of the cacheable prefix; different pages mean different cache keys)

### Requirement: PromptParts boundary type

The system SHALL define `PromptParts` as a frozen `@dataclass(slots=True)` in `src/a2web/packages/llm_extract/prompts.py` with three string fields: `system`, `cache_prefix`, `tail`. `PromptTemplate.render(content: str, ask: str) -> PromptParts` SHALL be defined on every template. For templates that do not opt in to caching, `cache_prefix` SHALL be the empty string and the rendered user message SHALL live entirely in `tail`.

#### Scenario: Cacheable template populates cache_prefix

- **WHEN** `EXTRACT_CACHEABLE_V1.render(content="<page>", ask="<q>")` is called
- **THEN** the returned `PromptParts.cache_prefix` is a non-empty string containing the page content

#### Scenario: Non-cacheable template degenerate shape

- **WHEN** `WEBFETCH_DEFAULT_V1.render(content="<page>", ask="<q>")` is called
- **THEN** the returned `PromptParts.cache_prefix` is `""` and `PromptParts.tail` carries the full formatted user message

### Requirement: AnthropicProvider sends explicit cache_control markers when given PromptParts

When `AnthropicProvider.complete()` is called with a `parts: PromptParts` argument whose `cache_prefix` is non-empty, the provider SHALL send the system block as a single text content item with `cache_control={"type": "ephemeral"}` and SHALL send the user content as a two-block list `[{"type":"text","text":parts.cache_prefix,"cache_control":{"type":"ephemeral"}}, {"type":"text","text":parts.tail}]`. When `parts` is `None` or `parts.cache_prefix == ""`, the provider SHALL fall back to the legacy single-string flat path with no cache_control markers (backwards compatible).

#### Scenario: Markers on cacheable path

- **WHEN** `AnthropicProvider.complete(parts=<non-degenerate parts>, ...)` is invoked
- **THEN** the underlying SDK call carries two user content blocks, the first with `cache_control={"type":"ephemeral"}`

#### Scenario: No markers on non-cacheable / legacy path

- **WHEN** `AnthropicProvider.complete(parts=None, ...)` or with degenerate parts is invoked
- **THEN** the underlying SDK call carries a single flat-string user content with no cache_control fields

### Requirement: ClaudeCodeProvider preserves byte-stable prefix without markers

`ClaudeCodeProvider.complete()` SHALL NOT introduce any `cache_control` marker code. When given `parts: PromptParts`, the provider SHALL pass `system_prompt=parts.system` to the SDK options and SHALL pass `prompt=parts.cache_prefix + parts.tail` (byte-equivalent concatenation) to `query()`. The byte-stability of the resulting concatenation across different `ask` values (guaranteed by the `EXTRACT_CACHEABLE_V1` template) SHALL be the sole compliance mechanism for the Claude Code SDK path. The Claude CLI binary applies caching internally given a stable prefix.

#### Scenario: Concatenated prompt is byte-stable across asks

- **WHEN** `ClaudeCodeProvider.complete(parts=parts1, ...)` and `ClaudeCodeProvider.complete(parts=parts2, ...)` are invoked with `parts1` and `parts2` produced by `EXTRACT_CACHEABLE_V1.render` for the same `content` but different `ask`
- **THEN** the concatenations `parts1.cache_prefix + parts1.tail` and `parts2.cache_prefix + parts2.tail` share an identical `parts.cache_prefix`-length byte-prefix

### Requirement: Default Extractor template

The production `Extractor` constructed by `build_llm_extractor` in `src/a2web/llm_resource.py` SHALL default to `EXTRACT_CACHEABLE_V1`. `WebFetchBaseline` in `src/a2web/llm_eval/` SHALL continue to use `WEBFETCH_DEFAULT_V1` (byte-frozen eval anchor; do not change).

#### Scenario: Production ask uses cacheable template

- **WHEN** `build_llm_extractor` constructs the production `Extractor`
- **THEN** its `template` attribute is `EXTRACT_CACHEABLE_V1`

#### Scenario: Eval baseline uses frozen template

- **WHEN** the eval suite constructs `WebFetchBaseline`
- **THEN** the underlying `Extractor.template` is `WEBFETCH_DEFAULT_V1`
