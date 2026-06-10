## 1. Event types

- [x] 1.1 Create `src/a2web/llm_eval/events.py` with frozen dataclasses `CellStarted` and `CellEnded` carrying the fields locked in design D1.
- [x] 1.2 ~~Register both event types on the suite's a2kit `App`~~ — **deviation:** the bench harness has no `App` (it composes resources via `bootstrap_state` directly). `a2kit.ldd.event(instance)` derives the payload via `dataclasses.asdict` without requiring registration; sinks receive `LddEmission(name=ClassName, payload={...})`. Tests confirm both flow correctly.

## 2. Live sink

- [x] 2.1 Create `src/a2web/llm_eval/live_sink.py` with a `LiveSink` class implementing `__aenter__` / `__aexit__` and subscribing to `CellStarted` + `CellEnded`.
- [x] 2.2 Internal state: `total` (set at construction), `done` counter, `running` counter, `cost_accumulator` float, `asyncio.Lock` for stdout, `tty` bool from `sys.stdout.isatty()`, `unicode` bool from stdout encoding probe.
- [x] 2.3 Implement `_format_start(event)` and `_format_end(event, counter)` matching the column spec in design D5 — counter (8) · marker (3) · slug (22) · system (18) · verdict (5) · duration (6) · cost (7) · trailing key=value pairs. ASCII fallback when `unicode=False`. Color only when `tty=True`.
- [x] 2.4 Implement the heartbeat task: 30s loop emitting `"… running: K, done: N/total, cost: $X.XX"` under the same lock. Cancel on `__aexit__`; await the cancellation cleanly.
- [x] 2.5 Failure-reason taxonomy: map exceptions and empty-answer cases in `_run_one` to the closed vocabulary (`system_raised`, `empty_answer`, `judge_failed`, `block_page`, `timeout`, `contract_violation`).

## 3. Wiring

- [x] 3.1 In `src/a2web/llm_eval/runner.py`, flip `_ldd_ambient` to `events_enabled=True, reports_enabled=False`.
- [x] 3.2 In `runner._run_one`, emit `CellStarted` at the top of the function and `CellEnded` at every exit (success path, system_raised path, empty-answer path, judge-failed path) — exactly one start, exactly one end, on every codepath.
- [x] 3.3 In `src/a2web/llm_eval/__main__.py`, instantiate `LiveSink(total=len(corpus) * len(systems))` and wrap `suite.run()` with `async with sink:`. Subscription happens via the `sinks=(live_sink,)` kwarg on `EvalSuite` (no `App` here — see 1.2 deviation), threaded into each `_ldd_ambient(sinks=...)` enter inside `_run_one`.

## 4. Tests

- [x] 4.1 Add `tests/capabilities/output_benchmark/test_live_sink.py` with a fake suite running 2 corpus × 2 systems through a stub EvalSystem that returns synthetic results. Assert exactly 4 `CellStarted` + 4 `CellEnded` events captured on a test sink.
- [x] 4.2 Assert the sink renders exactly 8 lines for the 4×2 cells (excluding heartbeat) with monotonically increasing `[i/N]` counters in completion order.
- [x] 4.3 Assert ordering invariant: every cell's end-line `[i/N]` appears later in stdout than its corresponding start-line for the same slug+system.
- [x] 4.4 Assert that a failure path (stub system raises) still produces exactly one `CellEnded` carrying `verdict="fail"` and a non-None `failure_reason`.
- [x] 4.5 Assert no heartbeat fires after the last `CellEnded` and before `__aexit__` returns.

## 5. Polish

- [x] 5.1 `make check` green (lint + ty + test ≥85% coverage).
- [x] 5.2 Add an internal-only entry to `CHANGELOG.md` under Unreleased: "bench: live per-cell stdout output via new LDD CellStarted/CellEnded events; 30s heartbeat".
- [x] 5.3 Update `CLAUDE.md` `events/` paragraph to mention `CellStarted` / `CellEnded` as bench-only event types under `llm_eval/events.py`.
