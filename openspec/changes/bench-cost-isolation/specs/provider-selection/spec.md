## ADDED Requirements

### Requirement: Metered API is opt-in in the bench context

In the benchmark/eval context, the metered `anthropic` provider SHALL be opt-in, never a silent fallback of the auto-order. When the subscription (`claude-code`) session is undetected, the bench SHALL fail loud (`LLMNotAvailable`) rather than silently selecting metered `anthropic`. Metered `anthropic` SHALL be reachable only via an explicit opt-in, and even then only for cheap models per the cost guard.

#### Scenario: undetected subscription session fails loud

- **WHEN** the bench runs with the default provider preference and no Claude Code OS session is detected
- **THEN** it raises `LLMNotAvailable` instead of falling through to metered `anthropic`

#### Scenario: explicit opt-in still cost-guarded

- **WHEN** metered `anthropic` is explicitly opted into and a Sonnet/Opus model is resolved
- **THEN** the cost guard raises `CostViolation` (opt-in does not bypass the model policy)
