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

The fallback preference order and the `_manifests.llm_providers` surface path SHALL each be declared exactly once in `src/a2web/`. The auto order SHALL prefer the credential-free backend (`claude-code`), then the API-key backend (`anthropic`), then `openai_compatible` as the LAST-resort fallback. Placing `openai_compatible` last means a configured `OPENAI_API_KEY` can never shadow a working Claude/Anthropic path — the derived fallback activates only when neither is available.

#### Scenario: Order tuple is not duplicated

- **WHEN** an architecture test scans `src/a2web/` for the provider fallback-order tuple and the `"a2web._manifests.llm_providers"` surface string
- **THEN** each appears in exactly one module

#### Scenario: Auto resolves to claude-code-first

- **WHEN** `select_provider(settings)` runs with `settings.llm_provider == "auto"` and both Anthropic backends are registrable
- **THEN** it returns `claude-code`

#### Scenario: openai_compatible never shadows a preferred backend

- **WHEN** `select_provider(settings)` runs with `settings.llm_provider == "auto"`, an `openai_compatible` endpoint is keyed, AND a Claude/Anthropic backend is registrable
- **THEN** the preferred backend wins (`openai_compatible` is last in the order, entered only when the preferred backends are absent)

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

### Requirement: OpenAI-compatible derives as the gated fallback

The `openai_compatible` backend SHALL be selected either by explicit pin (`settings.llm_provider == "openai_compatible"`) OR, under `auto`, as the last-resort fallback when no preferred backend is available — gated on its manifest being registrable (a resolvable `OPENAI_API_KEY` and model, per the provider spec). When it is unconfigured (no key, or an unresolvable model), it SHALL be absent from the registry, so an explicit pin yields the none sentinel rather than a silent degrade.

#### Scenario: Derived fallback when preferred backends are absent

- **WHEN** `settings.llm_provider == "auto"`, no `claude-code`/`anthropic` backend is registrable, and `openai_compatible` is keyed and model-resolved
- **THEN** `select_provider(...)` returns `openai_compatible` — derived with no explicit pin (the headless-container case)

#### Scenario: Explicit pin selects it

- **WHEN** `settings.llm_provider == "openai_compatible"` and the backend is registrable
- **THEN** it returns `openai_compatible`, never an Anthropic backend

#### Scenario: Pin without configuration yields none

- **WHEN** `settings.llm_provider == "openai_compatible"` but no `OPENAI_API_KEY` is set (or the model cannot be resolved)
- **THEN** `select_provider(...)` returns the none sentinel — the pin does not silently degrade to `claude-code`/`anthropic`

### Requirement: claude-code is optional at the packaging layer

`claude-agent-sdk` is an optional extra (`[claude-code]`), so the `claude-code` provider MAY be absent from an install. When the SDK is not importable, the `claude-code` manifest factory SHALL report `Unavailable` and provider auto-selection SHALL fall through to the next available backend (`anthropic`, or `openai_compatible` by pin) without crashing and without silently disabling `ask`. When the SDK is present, `claude-code` remains first in the auto order as before.

#### Scenario: Slim install degrades to anthropic

- **WHEN** `claude-agent-sdk` is not installed, `ANTHROPIC_API_KEY` is set, and `select_provider(settings)` runs with `llm_provider == "auto"`
- **THEN** the `claude-code` manifest reports `Unavailable`, auto-select returns `anthropic`, and `ask` works

#### Scenario: Slim install with no configured backend fails loud, not silent

- **WHEN** `claude-agent-sdk` is absent and no `anthropic`/`openai_compatible` backend is configured
- **THEN** selection returns the none sentinel and the extraction path surfaces an explicit unavailable signal — never an empty-but-`ok` answer

#### Scenario: Full install still prefers claude-code

- **WHEN** the `[claude-code]` extra is installed and both Anthropic backends are registrable under `llm_provider == "auto"`
- **THEN** auto-select returns `claude-code`, unchanged from prior behavior

