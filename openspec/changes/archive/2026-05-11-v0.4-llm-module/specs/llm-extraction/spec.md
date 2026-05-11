# llm-extraction (new)

## Purpose

Provides server-side LLM extraction over fetched content. Mirrors the trick used by Claude Code's `WebFetch` (research/123): run a small fast model over the already-fetched markdown using a fixed prompt template + a caller-supplied question, return only the answer. Replaces the need for the calling agent to ingest the full content envelope when it only wants a specific answer.

## ADDED Requirements

### Requirement: Extractor accepts content + ask and returns ExtractionResult

`Extractor(model: ModelSpec, template: PromptTemplate, cache: ExtractionCache | None)` SHALL expose `extract(content: str, ask: str) -> ExtractionResult`.

`ExtractionResult` SHALL be a `dataclass(slots=True)` with:
- `answer: str`
- `model: str` — exact model id used
- `template_name: str` — e.g. `"webfetch_default_v1"`
- `prompt_tokens: int`
- `completion_tokens: int`
- `cost_usd: float` — 0.0 on cache hit
- `original_cost_usd: float | None` — set on cache hit to record what the call would have cost
- `latency_ms: int`
- `cache_hit: bool`

#### Scenario: extract returns a populated result

- **GIVEN** a configured Extractor with the Anthropic provider and Haiku 4.5 model
- **WHEN** `extract(content="Rust was designed by Graydon Hoare in 2006.", ask="Who designed Rust?")` is invoked
- **THEN** the result's `answer` contains "Graydon Hoare"
- **AND** `prompt_tokens > 0` and `completion_tokens > 0` and `cost_usd > 0`
- **AND** `cache_hit is False`

#### Scenario: identical inputs hit the cache

- **GIVEN** the same Extractor is invoked twice with the same `(content, ask, model)`
- **WHEN** the second call runs
- **THEN** `cache_hit is True` and `cost_usd == 0.0`
- **AND** the answer is identical to the first call
- **AND** the second call's latency is below 50 ms

### Requirement: Prompt templates are frozen and named

`PromptTemplate` SHALL be a `@dataclass(frozen=True)` carrying `name: str`, `version: int`, `system: list[str]`, `user_template: str`. Templates SHALL be defined as module-level constants in `src/a2web/llm/prompts.py`.

The `WEBFETCH_DEFAULT_V1` template SHALL be byte-for-byte identical to Claude Code's `Rb9` non-preapproved-host user template as documented in research `~/Documents/Knowledge/Researches/123-claude-code-webfetch-internals/readme.md`, with `system=[]`.

#### Scenario: webfetch_default_v1 reproduces the binary template

- **WHEN** `WEBFETCH_DEFAULT_V1.user_template` is formatted with `{content}` and `{ask}`
- **THEN** the resulting string SHALL include the "Provide a concise response based only on the content above" guidance followed by the 4-bullet quote / OSS / lawyer / lyrics rules verbatim

### Requirement: Provider protocol supports empty system + thinking-disabled

`Provider.complete` SHALL accept `system: list[str] | str` (where `[]` produces a request with no system content) and `thinking_disabled: bool = True` (which SHALL disable extended thinking on providers that support it). This is required for WebFetch behavioral parity.

#### Scenario: Anthropic provider accepts empty system

- **WHEN** `AnthropicProvider.complete(system=[], user="hi", model="claude-haiku-4-5-20251001", thinking_disabled=True)` is invoked
- **THEN** the underlying API call SHALL be made with no system content (or empty array) and `thinking: {type: "disabled"}`
- **AND** the call succeeds

### Requirement: Missing `[llm]` extra raises LLMNotAvailable, not ImportError

When the `a2web.llm` module is imported but the underlying SDK (`anthropic`, `openai`) is not installed (i.e. the `[llm]` extra was not selected), module load SHALL succeed. The error SHALL surface only when extraction is attempted, as a `LLMNotAvailable` exception with an actionable message including the install command.

#### Scenario: bare install can still import a2web.llm

- **GIVEN** `pip install a2web` (no `[llm]` extra)
- **WHEN** `from a2web.llm import Extractor, ModelSpec` is executed
- **THEN** the import succeeds

#### Scenario: extraction attempt without the extra raises LLMNotAvailable

- **GIVEN** the bare install above
- **WHEN** `Extractor(model=ModelSpec("anthropic", "claude-haiku-4-5-20251001")).extract(content="...", ask="...")` is awaited
- **THEN** `LLMNotAvailable` is raised with a message containing `"pip install a2web[llm]"`
