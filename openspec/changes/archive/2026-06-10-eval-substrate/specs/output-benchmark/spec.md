## ADDED Requirements

### Requirement: deterministic axes gate make check; LLM-judged axes stay informational under make bench

The four-axis benchmark SHALL be split by determinism. The deterministic axes (data-contract
conformance, token cost, tier path / answer-envelope shape) SHALL run on frozen replay fixtures
and gate `make check`. The LLM-judged axes (answer quality, output clarity, `next_links` quality)
SHALL remain live and informational under `make bench` and SHALL NOT gate `make check`.

#### Scenario: a contract regression fails make check

- **WHEN** a code change makes a replayed case violate its `contract.json` (field presence, token
  bound, or tier path)
- **THEN** `make check` fails on the deterministic replay test, without invoking a live LLM judge

#### Scenario: an answer-quality delta is reported but does not gate

- **WHEN** `make bench` records a change in the LLM-judged answer-quality score
- **THEN** it appears in the dated run report as informational, and `make check` is unaffected

### Requirement: the judge model is pinned and recorded per run

When LLM-judged axes run under `make bench`, the judge model identifier SHALL be pinned and recorded
in the run report, so a quality delta between two runs is attributable to the system under test rather
than to judge-model drift.

#### Scenario: the run report records the judge model

- **WHEN** a `make bench` run completes
- **THEN** its report records the exact judge model id used for the LLM-judged axes
