## MODIFIED Requirements

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

## ADDED Requirements

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
