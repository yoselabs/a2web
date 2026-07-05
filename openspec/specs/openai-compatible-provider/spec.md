# openai-compatible-provider Specification

## Purpose
TBD - created by archiving change openai-compatible-llm-provider. Update Purpose after archive.
## Requirements
### Requirement: OpenAI-compatible completion backend

a2web SHALL provide an `openai_compatible` provider that satisfies the text-in/text-out `Provider` protocol (`complete(system, user, model, ...) -> ProviderResponse`) by calling an OpenAI-compatible `chat/completions` endpoint through the `openai` SDK (`AsyncOpenAI(base_url=, api_key=)`). The provider SHALL NOT depend on JSON-mode, tool-use, or streaming — the extractor prompts for JSON in text and the wobble funnel parses it, identical to the Anthropic path.

#### Scenario: Completes against a configured endpoint

- **WHEN** the provider's `complete(...)` is called with a configured `base_url`, `api_key`, and `model`
- **THEN** it issues one `chat/completions` request to that endpoint and returns a `ProviderResponse` whose `text` is the first choice's message content

#### Scenario: API failure returns an empty-text response, not a crash

- **WHEN** the endpoint returns an API error (non-2xx, timeout, malformed body)
- **THEN** `complete(...)` returns a `ProviderResponse` with empty `text`, the `model`, a measured `latency_ms`, and error detail on `raw` — mirroring `AnthropicProvider`'s error contract (the extractor's never-silently-miss handling owns the downstream signal)

### Requirement: Usage and cost accounting from OpenAI usage shape

The provider SHALL map the OpenAI usage object (`prompt_tokens` / `completion_tokens`) onto `ProviderResponse.prompt_tokens` / `completion_tokens`. When the model's price is unknown, `cost_usd` SHALL be `0.0` (the documented "could not price" sentinel), never a fabricated figure.

#### Scenario: Token counts flow from OpenAI usage

- **WHEN** a completion returns a usage object with `prompt_tokens` and `completion_tokens`
- **THEN** the `ProviderResponse` carries those counts unmodified

#### Scenario: Unknown model prices as zero, not guessed

- **WHEN** the response is for a model with no entry in the provider's price table
- **THEN** `cost_usd == 0.0` and callers are not given an invented price

### Requirement: Standard OpenAI env vars, config-gated construction

The provider SHALL read its endpoint and key from the **standard** OpenAI SDK environment variables — `OPENAI_API_KEY` (via a retained key-env-name indirection defaulting to `OPENAI_API_KEY`) and `OPENAI_BASE_URL` — rather than custom a2web-specific vars. The only a2web-native knob is the provider selector `A2WEB_LLM_PROVIDER=openai_compatible`. Construction SHALL succeed only when the key is present; absent it, the manifest factory SHALL return `Unavailable` with a reason and SHALL NOT raise at import or registration time. `OPENAI_BASE_URL` unset SHALL default to OpenAI proper.

#### Scenario: Missing key yields Unavailable, not an error

- **WHEN** the manifest factory runs with no `OPENAI_API_KEY` (nor the configured key-env) present
- **THEN** it returns `Unavailable(...)` with a human-readable reason, and the surface loader drops it silently

#### Scenario: Standard env vars build the provider

- **WHEN** `OPENAI_API_KEY` resolves to a non-empty value (with `OPENAI_BASE_URL` optionally set for a compat backend)
- **THEN** the manifest factory returns a constructed `openai_compatible` provider registered under that id, wired to that endpoint and key

### Requirement: Model resolution with curated recommendations, fail-loud on unknown

The model SHALL resolve as: explicit `OPENAI_MODEL` env → else the recommended default for the recognized `OPENAI_BASE_URL` host → else a loud failure (`LLMNotAvailable`) that lists the recommendations. It SHALL NOT fall back to the Anthropic `llm_model` default (which would send a Claude id to an OpenAI endpoint). Applying a recommended default SHALL emit an info log naming the model, host, and the `OPENAI_MODEL` override.

#### Scenario: Explicit model wins

- **WHEN** `OPENAI_MODEL` is set
- **THEN** that model id is used verbatim, regardless of host

#### Scenario: Recognized host supplies a logged default

- **WHEN** `OPENAI_MODEL` is unset and `OPENAI_BASE_URL` matches a recognized host (e.g. OpenAI or the Gemini compat host)
- **THEN** the curated recommended model for that host is used, and an info log names the model + host + how to override

#### Scenario: Unknown host with no model fails loud

- **WHEN** `OPENAI_MODEL` is unset and the host is unrecognized (local/gateway)
- **THEN** construction fails loud with a message listing the recommendations — never a silent wrong-model call

### Requirement: Custom models are evaluable through the existing bench

Validating an arbitrary OpenAI-compatible model SHALL reuse the existing benchmark harness via provider selection — no separate eval system. Pointing the bench at the backend (`A2WEB_BENCH_PROVIDER=openai_compatible` + the standard env) SHALL run the full extraction pipeline through that model and score it, with the data-contract axis (router-shape JSON / `next_links`) serving as the custom-model pass/fail gate.

#### Scenario: Bench runs end-to-end through a configured custom model

- **WHEN** the bench is invoked with `A2WEB_BENCH_PROVIDER=openai_compatible` and the standard OpenAI env configured
- **THEN** `A2WebExtract` runs its extraction through that model and produces four-axis scores including data-contract conformance, with no code path forked for the eval

