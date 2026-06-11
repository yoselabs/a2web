# Spike: bench shutdown-thread-leak

Date: 2026-05-26
Backlog: `BACKLOG.md:111` — `bench-shutdown-thread-leak` (filed 2026-05-25 v0.23 run)

## What the leak looks like

After `make bench` finishes the matrix and `write_all(report)` returns, the
process hangs in `Py_FinalizeEx → wait_for_thread_shutdown` on a non-daemon
background thread parked in `_queue_SimpleQueue_get` (a `queue.SimpleQueue.get()`
call in C). Bench output is fully written; only the exit blocks. Operator
workaround today: SIGKILL after the JSON stats dump.

## Diagnosis

`_queue_SimpleQueue_get` narrows the suspect set to threads waiting on
`queue.SimpleQueue` (NOT `queue.Queue`). The two consumers of `SimpleQueue`
in our dependency closure:

1. **`concurrent.futures.thread.ThreadPoolExecutor`** — uses `SimpleQueue` for
   its work queue. asyncio's *default* executor is shut down by
   `asyncio.run()` automatically, but any explicitly-constructed executor is
   not.
2. **`anyio` v4 `WorkerThread`** — uses `queue.Queue`, NOT `SimpleQueue`.
   Ruled out by symbol name.

Path A confirmed in the dep tree:
- `claude-agent-sdk` (default bench provider via `_pick_provider`) shells out
  through `anyio.open_process` + `anyio.to_thread.run_sync` for `_find_cli`.
  anyio's WorkerThread cleanup IS wired via
  `root_task.add_done_callback(worker.stop)` (`_backends/_asyncio.py:2488`),
  AND uses `queue.Queue` not `SimpleQueue` — so not this one.
- Strongest remaining candidate: **a ThreadPoolExecutor created by one of**
  curl_cffi, trafilatura, or the structlog/OTel chain. `curl_cffi` is C-side
  libcurl multi handle — possible thread leak there. Unconfirmed; would need
  the actual bench run with `faulthandler.dump_traceback_later` to name it.

## Small repro attempted

`scripts/spike_shutdown_leak.py` — drives `claude-agent-sdk.query()` x3
concurrently with production iteration shape (full-drain, no `break` on
ResultMessage), then arms a 5s SIGALRM watchdog. Result: **clean exit**.
Conclusion: at concurrency 3 with the SDK alone, shutdown is clean. The leak
needs the full bench surface (browser pool + sqlite + extraction cache +
concurrency=4 across 99 cells) — too expensive to repro outside of live
`make bench`.

Tangential finding from the repro: when the consumer breaks early on
ResultMessage instead of draining, asyncio emits
`RuntimeError: aclose(): asynchronous generator is already running` during
`shutdown_asyncgens()`. Production code already drains fully — not a bug — but
worth documenting that early-break would be wrong.

## Why "wrap extractor in bench __aenter__" won't help

I initially suspected `llm_eval/__main__.py:149` was the bug — only
`browser_pool` is async-with'd; `llm_extractor` and `cookie_jar` are
constructed by `bootstrap_state` but never lifecycled. Reading
`LlmExtractorResource.close()` (`src/a2web/llm_resource.py:164`) shows it's a
**no-op**. Wrapping it would not change the shutdown sequence. The leaking
thread is created inside one of the per-call paths (curl_cffi or similar),
not on `LlmExtractor` construction, so no entry/exit hook on the resource
would catch it.

## Recommended fix (S, low risk)

Add an explicit `os._exit(0)` at the tail of `llm_eval/__main__.py::main()`
after the stats dump. Justification:

- The bench is a one-shot CLI with no graceful-shutdown contract to honor —
  no in-flight network requests, no open writers, no cleanup that
  `asyncio.run` hasn't already done.
- All sinks have already flushed: `write_all(report)` is sync and finished;
  `print(json.dumps(stats_dict))` is line-buffered through stdout.
- `os._exit` bypasses `Py_FinalizeEx` thread-joining, eliminating the hang.
- Trade-off: no atexit hooks run. We have none registered (a2kit lifecycle
  uses `__aexit__`, which already fired in `async with` blocks).

This is a documented workaround, not a root-cause fix. The proper fix lives
upstream (whichever dep is the culprit). To narrow it down, the next step
would be to enable `faulthandler.dump_traceback_later(60)` in a live bench run
and grep the traceback for the parked thread's filename — the fastest path
to upstream attribution.

## Decision

Ship `os._exit(0)` workaround in `__main__.py`. Keep the BACKLOG.md entry open
(downgrade is fine — operator pain is now zero). Re-open with upstream
identification once we have a faulthandler trace from a real bench run.

### Landed 2026-06-11

The workaround was recommended here but never actually applied — the
2026-06-11 post-v0.43-migration bench run hit the hang again (with Camoufox
subprocesses lingering, since the hung parent never died). Now landed:
`main()` flushes stdout/stderr and calls `os._exit(rc)` after `asyncio.run`
returns. Mechanism verified deterministically: a non-daemon thread parked on
`queue.SimpleQueue.get()` hangs a normal interpreter exit (reproduces
`Py_FinalizeEx → wait_for_thread_shutdown`), while `os._exit` exits cleanly.
The Camoufox orphan is also resolved — it lingered only because the hung
Python parent stayed alive; on `os._exit` the parent dies and Camoufox reaps
via its parent-death pipe. Upstream attribution (which dep) remains open.

## Files touched

- `scripts/spike_shutdown_leak.py` — repro harness (keep for future probes).
- `eval/findings_2026-05-26-shutdown-thread-leak-spike.md` — this file.
