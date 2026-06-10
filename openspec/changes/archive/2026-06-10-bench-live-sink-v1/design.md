## Context

`make bench` runs `python -m a2web.llm_eval`, which builds a (corpus × systems) matrix and processes cells under bounded concurrency via `asyncio.gather` in `EvalSuite.run()`. A typical run is 30 URLs × 3 systems = 90 cells, ~10 minutes wall-clock end-to-end.

Today's harness sets up an LDD ambient via `_ldd_ambient()` in `llm_eval/runner.py:48` with `events_enabled=False, reports_enabled=False`. The flag was set this way so the production `a2web.orchestrator` `StageStarted`/`StageEnded` events — which fire dozens of times per page extraction — don't drown out the harness output. With both bus channels muted, the entire run is silent until `write_all(report)` dumps the final JSON.

Constraints:
- Cells run concurrently (default `--concurrency=4`), so any console writer must serialize.
- The production orchestrator emits its own LDD events that we deliberately want to keep silent during bench.
- The LDD bus is owned by `a2kit.ldd` — adding new event types is the documented extension path.
- `packages/` independence: the events must NOT live in `src/a2web/packages/` (would couple a package to bench-only types).

## Goals / Non-Goals

**Goals:**
- Every (corpus × system) cell emits a visible start + end line.
- Concurrent cells don't interleave on stdout.
- Heartbeat catches "is it stuck?" between cell-end lines (30s).
- Failure cases surface a one-word reason on the end line, not a stack.
- Zero changes to production orchestrator behavior or trace-file contents.
- `make check` stays green; one new capability test asserts the invariants.

**Non-Goals:**
- Structured-JSON or NDJSON output mode for the bench (sink is the seam — add later if needed).
- Per-tier or per-stage visibility in the bench output (already in `trace/` files).
- Surfacing the production `StageStarted`/`StageEnded` chatter — those stay muted.
- Replacing the final JSON stats dump or the `report.write_all(...)` output.
- Re-architecting the LDD bus or its sink mechanism.

## Decisions

### D1 — Two new event types, scoped to bench

`CellStarted(slug, system_name, url, started_at)` and `CellEnded(slug, system_name, url, total_ms, verdict, failure_reason, cost_usd, cache_hit, tier)` live in `src/a2web/llm_eval/events.py` as frozen dataclasses. Registered against `app.ldd.events.register(...)` at suite construction.

**Alternative considered:** reuse the existing `StageStarted`/`StageEnded` types and tag with a `kind="bench-cell"` field. Rejected — those are domain-level production events; conflating bench-harness signals with them muddies both consumers (OTel sink in particular).

### D2 — Counter assigned at completion, not launch

`[i/N]` is claimed inside the sink's `CellEnded` handler under the lock, so the counter reflects completion order (matching what the operator sees). Launch order is implementation detail (`asyncio.gather` task scheduling).

**Alternative considered:** claim counter at `CellStarted`. Rejected — with concurrency >1 the start lines arrive in a different order than ends, leading to non-monotonic `[i/N]` jumps that read as out-of-order rather than progress.

The start line uses a placeholder marker (`▶`) without a counter; the end line carries `[i/N]`. This is asymmetric but matches what the operator wants: "tell me what started" (no counter needed, it's an event signal) vs. "tell me how far we are" (counter on completion).

### D3 — Lock-serialized stdout writes; no buffering

`LiveSink` holds an `asyncio.Lock`. Each handler acquires the lock, formats the line, writes via `sys.stdout.write(...) + flush()`, releases. No internal buffer — a SIGINT mid-run still leaves a clean line on the terminal.

### D4 — Heartbeat as an `asyncio.Task` owned by the sink

The sink starts a heartbeat task in `__aenter__` that loops on `asyncio.sleep(30)` and emits a one-line summary derived from sink-internal counters (`running`, `done`, `total`, `cost_accumulator`). Task is cancelled in `__aexit__`.

**Alternative considered:** wall-clock cron via the harness. Rejected — the sink owns the counters; bouncing through the harness adds a coupling for no gain.

### D5 — Format chosen for terminal width 80–120, no color by default

```
[1/30]  ▶  reddit-thread          A2WebDetail        start
[1/30]  ✓  reddit-thread          A2WebDetail        ok    1.2s  $0.003  cache=miss tier=raw
[2/30]  ✗  hn-front               WebFetchBaseline   fail  4.1s  $0.001  block_page
```

Columns: counter (8) · marker (3) · slug (22 left-aligned, truncated) · system (18) · verdict (5) · duration (6) · cost (7) · trailing key=value pairs.

Color (green `✓`, red `✗`) gated on `sys.stdout.isatty()` — CI logs stay plain. Markers are unicode glyphs (`▶ ✓ ✗`) consistent with the project's existing structlog/diagnostics style; fall back to ASCII (`> + !`) if stdout encoding isn't UTF-8.

### D6 — Flip `_ldd_ambient` to events-on, reports-off

`events_enabled=True` lets `CellStarted`/`CellEnded` (and the production `StageStarted`/`StageEnded`) flow on the bus; the sink subscribes only to the cell events, so stage chatter is dropped at the subscriber level, not at the bus level. `reports_enabled=False` stays — bench cells don't produce MCP envelope reports.

**Alternative considered:** add a per-event filter to `_ldd_ambient` (mute everything except cell events). Rejected — adds a per-event check to the bus hot path for a one-off case; subscriber-side filtering is cheaper and isolated to the bench harness.

### D7 — Failure reason taxonomy

`CellEnded.failure_reason` is `None` on success or a short closed-vocabulary string on failure: `"system_raised"`, `"empty_answer"`, `"judge_failed"`, `"block_page"`, `"timeout"`, `"contract_violation"`. Mapped at the call site in `_run_one`. Operators don't get a stack — for diagnosis they read `cell_dir/row.json` in the trace tree.

## Risks / Trade-offs

- [Heartbeat fires after run end if cancellation lags] → `__aexit__` awaits the heartbeat task's cancellation; the test asserts no heartbeat after `CellEnded` of the last cell.
- [Stdout interleaving with the trailing JSON stats dump] → suite writes its final lines after the sink's `__aexit__`, so the heartbeat task is gone by then. Test covers ordering.
- [Color codes leak into log files when `make bench` is piped] → guarded by `sys.stdout.isatty()`; piped invocations strip color automatically.
- [Subscribing to cell events couples bench to a2kit LDD subscriber API] → a2kit owns the bus and the API is stable since v0.39; tracked at the same dependency line as the rest of `a2kit.ldd.event(...)`.
- [Concurrent cells share the lock — could serialize on slow terminals] → write-and-flush per cell is microseconds even with TTY render; concurrency 4 × 90 cells = ~360 writes per run, negligible.

## Migration Plan

Single commit. No persisted state. No rollback needed beyond reverting the commit. CHANGELOG gets a one-line internal note; no user-facing entry (bench is internal tooling).
