## ADDED Requirements

### Requirement: Bench asserts model cost before every LLM call

Every LLM completion issued by the benchmark SHALL pass through a cost guard on the resolved `(provider, model)` pair *before the call is issued*, raising `CostViolation` when the pair is not cheap-approved. The benchmark SHALL acquire its provider only through a factory that wraps the provider's completion in this guard, so no un-guarded completion path exists. The default policy SHALL allow subscription (`claude-code`) with any model, allow metered `anthropic` only with cheap models (Haiku), allow `openai_compatible` only for an explicit cheap allowlist, and DENY metered `anthropic` with Sonnet/Opus, `openai_compatible` with gpt-4-class models, and any unknown pair.

#### Scenario: expensive metered pair is refused before spending

- **WHEN** the bench resolves to `provider=anthropic, model=claude-sonnet-*` (e.g. subscription session undetected)
- **THEN** the guard raises `CostViolation` before any completion is issued — no tokens are billed

#### Scenario: subscription may use any model

- **WHEN** the bench resolves to `provider=claude-code` with a Sonnet judge model
- **THEN** the guard permits the call (subscription is flat-cost)

#### Scenario: no un-guarded path

- **WHEN** any bench code path issues a completion (system, quality judge, clarity judge, next_links judge)
- **THEN** that completion went through the cost guard (the provider was obtained pre-wrapped)

### Requirement: Bench run artifacts stamp the provider and model used

Every benchmark run artifact SHALL record the resolved `provider` and `model` actually used, both in the run header and per cell. A run that used the metered API SHALL be identifiable from its own artifact.

#### Scenario: artifact carries provenance

- **WHEN** a bench run completes
- **THEN** its artifact under `eval/runs/` records `provider` and `model` for the run and for each cell

### Requirement: Bench supports per-item and per-axis isolation

The benchmark SHALL support running a single corpus item (via a `--slug`/`--id` filter, finer than the existing `--only <class>`) and a single scoring axis (via per-axis select/skip flags). An item filter matching zero items SHALL fail loud. With no isolation flags, all items and all axes SHALL run (current behavior preserved).

#### Scenario: single item, single axis

- **WHEN** the bench is run with an item filter naming one corpus item and an axis filter naming `quality`
- **THEN** only that item runs, only the quality axis is scored, and the total LLM-call count is a small handful (not the full matrix)

#### Scenario: unknown item fails loud

- **WHEN** the item filter matches no corpus item
- **THEN** the bench exits with a clear error rather than silently running the full corpus
