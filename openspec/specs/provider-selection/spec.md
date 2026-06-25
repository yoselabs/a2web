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

### Requirement: Provider is injected into the extraction resource

The extraction resource SHALL receive its `Provider` by injection and SHALL NOT select a provider internally. In production the provider is supplied by the DI container via a `Provider` factory whose body is the shared `select_provider`; outside the container (bench, tests) the provider is supplied directly as a `Lazy[Provider]`. The resource resolves provider construction lazily on first use, preserving cold start.

#### Scenario: Production resolves the provider through DI

- **WHEN** a tool first awaits the LLM resource and a provider is configured
- **THEN** the resource obtains its `Provider` from the injected `Lazy[Provider]` (resolved by the DI-registered factory), having performed no selection of its own

#### Scenario: Bench supplies one provider to both judge and extraction

- **WHEN** the bench resolves a provider for its judges
- **THEN** the same provider instance is supplied to the extraction resource, with no `settings.llm_provider` mutation used to steer a second internal selection

#### Scenario: Tests inject a fake provider without touching internals

- **WHEN** a test needs the extraction resource to use a specific stub provider
- **THEN** it supplies that provider through the injection seam (a `Lazy[Provider]` or a DI override), not by assigning the resource's private `_extractor`/`_unavailable_reason`

### Requirement: One unavailability path for a missing provider

"No LLM provider available" SHALL travel the single `ResourceUnavailable` seam shared with other Lazy resources. The resource SHALL NOT carry a separate `unavailable_reason` state or return a sentinel `None` to signal absence; awaiting an unavailable provider SHALL raise `ResourceUnavailable`, carrying the human-readable reason.

#### Scenario: Missing provider degrades via the shared seam

- **WHEN** the `ask` path runs with no provider configured
- **THEN** awaiting the provider raises `ResourceUnavailable`, the orchestrator catches it at one site, and emits the `llm_unavailable` OperatorHint (degrading to raw fetch) — the same external outcome as before

#### Scenario: No second unavailability mechanism remains

- **WHEN** the extraction phase handles a missing LLM
- **THEN** it does so through exactly one `except ResourceUnavailable`, with no `extract() is None` check and no read of an `unavailable_reason` attribute

