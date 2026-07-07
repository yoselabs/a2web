## ADDED Requirements

### Requirement: the benchmark emits a structured results.json with a cost summary

Each benchmark run SHALL write a machine-readable `results.json` alongside the
existing outputs, containing one object per (corpus × system) cell (its axis
scores plus `fetch_cost_usd`, fetch prompt/completion token counts, and
`judge_cost_usd`) and a top-level `summary` that rolls up `total_cost_usd` and
total prompt/completion tokens for the run, both overall and per system. The
cost and token values SHALL be the ones already reported by the provider (the
claude-code SDK's `ResultMessage` on the subscription path), not re-derived. The
existing `results.tsv` / `manifest.json` / `cost.md` outputs are unaffected.

#### Scenario: a run writes results.json with rows and a summary

- **WHEN** a benchmark run completes
- **THEN** `results.json` exists with a `rows` array (one entry per scored cell) and a `summary` object
- **AND** the summary reports `total_cost_usd` and total prompt/completion tokens overall and per system

#### Scenario: results.json agrees with results.tsv

- **WHEN** both files are written for the same run
- **THEN** `results.json.rows` has the same cell count as `results.tsv`, deriving from the same report rows

### Requirement: the benchmark can run a subset of the corpus by class

The benchmark CLI SHALL accept an `--only <class>` option that restricts the run
to corpus cases of the given class (e.g. `listing`), so a crucial subset can be
run without editing the corpus. When `--only` is absent the full corpus runs
(unchanged). When no case matches the requested class the run SHALL report a clear
"0 cases match" message naming the known classes and exit non-zero, so an empty
run is never mistaken for a pass.

#### Scenario: --only narrows the matrix to one class

- **WHEN** the benchmark is invoked with `--only listing`
- **THEN** only corpus cases of class `listing` are run (× the selected systems)

#### Scenario: an unknown class fails loudly

- **WHEN** `--only` names a class no case carries
- **THEN** the run prints a "0 cases match" message listing the known classes and exits non-zero
