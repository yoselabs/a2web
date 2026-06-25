## ADDED Requirements

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
