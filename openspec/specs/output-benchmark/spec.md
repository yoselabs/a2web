# output-benchmark Specification

## Purpose

The re-runnable output-quality benchmark contract: the four measurement axes (answer quality, token cost, output clarity, data-contract conformance), the `next_links_picked_correctly` axis on listing URLs, the corpus format and its required tricky-scenario coverage, the vs-WebFetch baseline, and the rule that the benchmark is package-resident and test-covered so it cannot silently rot. The benchmark observes the response envelope; it does not change any product capability.
## Requirements
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

### Requirement: the benchmark scores four axes per cell

For each (URL, system) cell the benchmark SHALL record four axes: answer quality (judge score against per-question criteria), token cost (tokens of the response envelope the agent must read), output clarity (how cleanly an agent can act on the output), and data-contract conformance. All four SHALL appear in the run report.

#### Scenario: a cell carries all four axes

- **WHEN** the benchmark scores one (URL, system) cell
- **THEN** the report row for that cell carries an answer-quality score, a token-cost number, an output-clarity score, and a data-contract-conformance result

#### Scenario: token cost measures the envelope

- **WHEN** the token-cost axis is recorded for an a2web system
- **THEN** it is the token count of the response envelope the agent receives, broken down by field — not the tokens of any internal LLM call

### Requirement: data-contract conformance is checked deterministically

The data-contract axis SHALL be a deterministic, non-LLM assertion that the a2web response envelope obeys its field-presence rules: `tier`, `url`, and `status` present only when they deviate from their default; the `debug` object present only under `debug=True`; `next_links` well-shaped when present. A violation SHALL be reported as a contract failure for that cell.

#### Scenario: a conformant envelope passes

- **WHEN** an a2web envelope obeys every field-presence rule
- **THEN** the data-contract axis for that cell reports conformance

#### Scenario: a deviation-field leak fails the axis

- **WHEN** an a2web envelope carries `tier`, `url`, or `status` at a non-deviating value, or carries `debug` without `debug=True`
- **THEN** the data-contract axis reports a contract failure naming the offending field

### Requirement: next_links candidate quality is scored on listing URLs

For listing-style corpus URLs the benchmark SHALL apply a `next_links_picked_correctly` judge axis assessing whether the `next_links` candidates are the right "what to fetch next" set for the task. Non-listing URLs SHALL NOT be scored on this axis.

#### Scenario: a listing URL is scored on next_links

- **WHEN** the benchmark runs a listing-style URL (e.g. a Reddit or HN listing, a PyPI or gh-trending page) through an a2web system
- **THEN** the report records a `next_links_picked_correctly` score for that cell

#### Scenario: a non-listing URL skips the axis

- **WHEN** the benchmark runs a permalink or article URL that has no drilldown layer
- **THEN** the `next_links_picked_correctly` axis is not scored for that cell

### Requirement: the corpus covers tricky scenarios

The benchmark corpus SHALL include the cases that break naive fetchers — Reddit comment threads, Hacker News comment/item pages, and index/listing pages — in addition to clean-HTML, gated, and SPA classes. Each corpus entry SHALL carry a task and pass/fail `criteria` phrased against stable structural facts so the entry survives page-content rotation.

#### Scenario: the corpus includes comment and listing pages

- **WHEN** the benchmark corpus is loaded
- **THEN** it contains at least one Reddit comment thread, one Hacker News comment/item page, and one index/listing page, each with a task and non-empty criteria

### Requirement: the benchmark compares against a WebFetch baseline without an API key

The benchmark SHALL include Claude Code's WebFetch as a baseline system run head-to-head with the a2web systems, produced automatically by the in-process `WebFetchBaseline` reproduction. The benchmark SHALL run on the `claude-code` provider (OAuth subscription) by default and SHALL NOT require `ANTHROPIC_API_KEY`; it MAY fall back to an API-key provider when the subscription provider is unavailable.

#### Scenario: the run includes the WebFetch baseline automatically

- **WHEN** the benchmark runs in its default mode
- **THEN** the report carries WebFetch-baseline rows alongside the a2web-system rows, with no interactive per-URL step

#### Scenario: the benchmark runs without an API key

- **WHEN** the benchmark is started with no `ANTHROPIC_API_KEY` set and Claude Code is logged in
- **THEN** the suite runs to completion using the `claude-code` provider for both the reader and the judge

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

