# provider-selection Specification

## Purpose
TBD - created by archiving change centralize-provider-selection. Update Purpose after archive.
## Requirements
### Requirement: Single provider-selection seam

LLM provider selection — choosing which provider backend to use from the manifest registry — SHALL be expressed by exactly one domain function. All production and bench call sites SHALL delegate to it rather than re-implementing the preference order, the explicit-pin rule, or the manifest surface path. The function SHALL return the chosen `(provider_id, provider)` pair, or a single "none available" sentinel; callers supply their own error-shaping around that result.

#### Scenario: Both call sites delegate to the shared selector

- **WHEN** an architecture test inspects `llm_resource._build()` and `llm_eval/__main__._pick_provider()`
- **THEN** neither contains its own provider-preference loop or fallback-order literal; both obtain their provider via the shared `select_provider(...)` function

#### Scenario: provider_id is the manifest name

- **WHEN** `select_provider(...)` returns a provider
- **THEN** the returned `provider_id` is the winning manifest's registry name (e.g. `"anthropic"` / `"claude-code"`), the same string `settings.llm_provider` accepts

### Requirement: Preference order has one source of truth

The fallback preference order and the `_manifests.llm_providers` surface path SHALL each be declared exactly once in `src/a2web/`. The order SHALL prefer the credential-free backend (`claude-code`) before the API-key backend (`anthropic`).

#### Scenario: Order tuple is not duplicated

- **WHEN** an architecture test scans `src/a2web/` for the provider fallback-order tuple and the `"a2web._manifests.llm_providers"` surface string
- **THEN** each appears in exactly one module

#### Scenario: Auto resolves to claude-code-first

- **WHEN** `select_provider(settings)` runs with `settings.llm_provider == "auto"` and both providers are registrable
- **THEN** it returns `claude-code`

### Requirement: Explicit pin overrides auto order

When a caller pins a specific provider — via `settings.llm_provider` set to a concrete id, or via an explicit `override` argument — selection SHALL attempt only that provider and SHALL NOT fall back to the auto order.

#### Scenario: Explicit anthropic forces anthropic

- **WHEN** `select_provider(settings)` runs with `settings.llm_provider == "anthropic"` and both providers are registrable
- **THEN** it returns `anthropic`, never `claude-code`

#### Scenario: Pinned-but-unavailable yields none

- **WHEN** a caller pins a provider that is not in the registry
- **THEN** `select_provider(...)` returns the none sentinel (the caller decides whether that is a silent degrade or a raised error)

### Requirement: Selection result carries no dead identity

The provider-identity surface SHALL carry no field that has no runtime reader. `ModelSpec` SHALL NOT retain a `provider` field or a `key()` method once they have no production consumer; the model-id string alone keys the extraction cache.

#### Scenario: ModelSpec exposes only the model id for keying

- **WHEN** the extraction cache computes its lookup/write key
- **THEN** the key derives from the model-id string and content/ask/template, not from any provider-id field on `ModelSpec`

#### Scenario: No Literal-narrowing ceremony for provider_id

- **WHEN** the bench resolves its provider id for downstream use
- **THEN** the id flows as a plain `str` (validated where it enters `AppSettings`), with no hand-written `Literal` narrowing branch

