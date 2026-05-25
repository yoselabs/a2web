## Why

`make bench` looks frozen. The harness fans out (corpus × systems) cells via `asyncio.gather` and prints nothing per cell — for a 30-URL × 3-system run that's ~10 minutes of total silence between the "Running benchmark…" header and the final JSON stats dump. Today's `_ldd_ambient()` in `llm_eval/runner.py` explicitly disables events and reports, so even the LDD bus is muted.

Operators can't tell whether the run is progressing, stuck on one URL, or burning quota on a system that's failing every cell. Log-driven dev says: every test should be visible.

## What Changes

- New `CellStarted` / `CellEnded` LDD events emitted from `runner._run_one` bracketing each (corpus_entry, system) cell.
- New `LiveSink` in `llm_eval/` that subscribes to those events and writes one line per cell to stdout, under an `asyncio.Lock` so concurrent cells don't interleave.
- New periodic `Heartbeat` line (every 30s while cells in-flight) showing `running: K, done: N/total, cost: $X.XX`.
- Flip `_ldd_ambient` from `events_enabled=False` to `events_enabled=True`. Reports stay disabled (those are MCP-envelope reports, irrelevant for bench).
- No change to the production a2web orchestrator's `StageStarted`/`StageEnded` events (those stay at extraction-granularity — too chatty for bench).
- No change to `trace/` file outputs (already correct).

## Capabilities

### New Capabilities
(none — this extends an existing capability)

### Modified Capabilities
- `output-benchmark`: add the live-output requirement — every cell emits a start + end signal, and `make bench` renders one line per signal plus a 30s heartbeat. The current spec assumes silent run + final report; this widens the contract to include in-flight visibility.

## Impact

- Affected code: `src/a2web/llm_eval/runner.py` (event emission + ambient flip), `src/a2web/llm_eval/__main__.py` (sink registration), new `src/a2web/llm_eval/live_sink.py` (~80 LOC), new `src/a2web/llm_eval/events.py` for the two event payloads.
- No public API change — bench is internal tooling.
- No tool-signature or response-envelope change.
- `packages/` independence intact — events live in `llm_eval/` (domain), not under `packages/`.
- New capability test in `tests/capabilities/output_benchmark/test_live_sink.py`.
