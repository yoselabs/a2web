## MODIFIED Requirements

### Requirement: the benchmark emits live per-cell signals on the LDD bus

For every (URL, system) cell, the benchmark SHALL emit one `CellStarted` event when the cell begins and exactly one `CellEnded` event when the cell finishes — including the failure path where the system raised or returned an empty answer. The events SHALL flow on the `a2web` logging path: `CellStarted` / `CellEnded` are defined in `src/a2web/llm_eval/events.py` and consumed by `src/a2web/llm_eval/live_sink.py::LiveSink` (a `logging.Handler`). `CellStarted` SHALL carry `slug`, `system_name`, `url`, and `started_at`. `CellEnded` SHALL carry `slug`, `system_name`, `url`, `total_ms`, a closed-vocabulary `verdict` (`ok` | `fail`), an optional closed-vocabulary `failure_reason` when the verdict is `fail`, `cost_usd`, `cache_hit`, and `tier`.

#### Scenario: every cell emits exactly one start and one end signal

- **WHEN** the benchmark runs a corpus of N URLs across M systems
- **THEN** the `a2web` logging path carries exactly N × M `CellStarted` events and exactly N × M `CellEnded` events for that run

#### Scenario: a failing cell still emits CellEnded

- **WHEN** a cell's system raises an exception or returns an empty answer
- **THEN** a single `CellEnded` event is still emitted carrying `verdict="fail"` and a closed-vocabulary `failure_reason`
