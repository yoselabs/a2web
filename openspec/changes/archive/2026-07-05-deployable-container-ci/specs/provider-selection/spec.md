## ADDED Requirements

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
