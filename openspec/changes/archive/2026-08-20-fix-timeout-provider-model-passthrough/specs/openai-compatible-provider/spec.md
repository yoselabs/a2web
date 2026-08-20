## MODIFIED Requirements

### Requirement: Model resolution with curated recommendations, fail-loud on unknown

The model SHALL resolve as: explicit `OPENAI_MODEL` env → else the recommended default for the recognized `OPENAI_BASE_URL` host → else a loud failure (`LLMNotAvailable`) that lists the recommendations. It SHALL NOT fall back to the Anthropic `llm_model` default (which would send a Claude id to an OpenAI endpoint). Applying a recommended default SHALL emit an info log naming the model, host, and the `OPENAI_MODEL` override. This resolution SHALL hold through provider selection's own wrapping (e.g. a request-timeout bound applied around the returned provider) — a wrapper that hides the resolved model from its caller is equivalent to not resolving one at all.

#### Scenario: Explicit model wins

- **WHEN** `OPENAI_MODEL` is set
- **THEN** that model id is used verbatim, regardless of host

#### Scenario: Recognized host supplies a logged default

- **WHEN** `OPENAI_MODEL` is unset and `OPENAI_BASE_URL` matches a recognized host (e.g. OpenAI or the Gemini compat host)
- **THEN** the curated recommended model for that host is used, and an info log names the model + host + how to override

#### Scenario: Unknown host with no model fails loud

- **WHEN** `OPENAI_MODEL` is unset and the host is unrecognized (local/gateway)
- **THEN** construction fails loud with a message listing the recommendations — never a silent wrong-model call

#### Scenario: Resolved model survives selection's wrapping

- **WHEN** the `openai-compatible` provider is obtained through the full provider-selection path (not a bare, unwrapped adapter) and its `default_model` is read back by the caller that resolves which model id to send
- **THEN** the caller observes the resolved model id — never the Anthropic default, and never an empty value that a caller-side `or` would silently replace
