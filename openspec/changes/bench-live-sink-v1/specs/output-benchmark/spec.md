## ADDED Requirements

### Requirement: the benchmark emits live per-cell signals on the LDD bus

For every (URL, system) cell, the benchmark SHALL emit one `CellStarted` event when the cell begins and exactly one `CellEnded` event when the cell finishes — including the failure path where the system raised or returned an empty answer. The events SHALL flow on the standard a2kit LDD event bus. `CellStarted` SHALL carry `slug`, `system_name`, `url`, and `started_at`. `CellEnded` SHALL carry `slug`, `system_name`, `url`, `total_ms`, a closed-vocabulary `verdict` (`ok` | `fail`), an optional closed-vocabulary `failure_reason` when the verdict is `fail`, `cost_usd`, `cache_hit`, and `tier`.

#### Scenario: every cell emits exactly one start and one end signal

- **WHEN** the benchmark runs a corpus of N URLs across M systems
- **THEN** the LDD bus carries exactly N × M `CellStarted` events and exactly N × M `CellEnded` events for that run

#### Scenario: a failing cell still emits CellEnded

- **WHEN** a cell's system raises an exception or returns an empty answer
- **THEN** a single `CellEnded` event is still emitted carrying `verdict="fail"` and a closed-vocabulary `failure_reason`

### Requirement: the benchmark renders one stdout line per cell signal

The benchmark CLI (`python -m a2web.llm_eval` / `make bench`) SHALL render exactly one stdout line per `CellStarted` event and exactly one stdout line per `CellEnded` event. The two lines SHALL share an `[i/N]` counter assigned at completion order — the `CellEnded` line carries the counter; the `CellStarted` line shows a start marker with no counter. Concurrent cells SHALL NOT interleave: each line is written atomically and flushed before the next acquires the writer.

#### Scenario: cell lines appear in completion order

- **WHEN** the benchmark runs with concurrency greater than one and cells finish out of launch order
- **THEN** the `[i/N]` counters in the stdout end-lines are monotonically increasing in completion order

#### Scenario: lines do not interleave under concurrency

- **WHEN** two cells finish at the same instant
- **THEN** their stdout lines appear one fully before the next — no character-level interleaving

### Requirement: the benchmark emits a periodic heartbeat while cells are in flight

The benchmark CLI SHALL emit a single-line heartbeat every 30 seconds while at least one cell is in flight, showing the count of running cells, the completed-over-total ratio, and the running cost-USD accumulator. The heartbeat SHALL stop before the final stats dump.

#### Scenario: a long-running cell produces heartbeats

- **WHEN** a cell takes longer than 30 seconds to complete
- **THEN** at least one heartbeat line appears between its start and end lines

#### Scenario: no heartbeat after the last cell

- **WHEN** the final cell of the run has emitted its `CellEnded` line
- **THEN** no further heartbeat lines appear before the final JSON stats dump

## MODIFIED Requirements

### Requirement: the benchmark is package-resident and re-runnable

The benchmark SHALL live inside the maintained package at `src/a2web/llm_eval/`, be type-checked and test-covered, and be invocable by a single command. It SHALL NOT be implemented as dated throwaway scripts outside the package. Re-running the benchmark after an envelope change SHALL require no edits to the harness. The benchmark SHALL also surface progress visibly on stdout — operators SHALL NOT need to read the `trace/` tree to know whether the run is alive.

#### Scenario: the benchmark runs from one command

- **WHEN** an operator runs the benchmark command (`make bench` / `python -m a2web.llm_eval`)
- **THEN** the full corpus × systems matrix runs and a dated report is written, with no manual per-URL steps

#### Scenario: an envelope change does not require harness edits

- **WHEN** the a2web response envelope changes in a spec-conformant way
- **THEN** the benchmark still runs unchanged, and any contract regression is reported by the data-contract axis rather than crashing the harness

#### Scenario: a long run shows progress without manual inspection

- **WHEN** an operator runs the benchmark on a corpus of 30+ URLs
- **THEN** they see one stdout line per cell start, one per cell end, and a heartbeat at least every 30 seconds while cells are in flight — without needing to tail any file
