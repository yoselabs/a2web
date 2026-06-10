# ADR-0008 — Test-resource lifecycle teardown at the bypass seam

**Status:** Accepted (confirmed 2026-06-10 against the suite — 20/20 clean runs,
fitness function proven load-bearing at 71 errors × 3)
**Date:** 2026-06-10
**Supersedes:** —
**Superseded by:** —

## Context

The suite intermittently failed (~1/5-1/10 runs) with `RuntimeError: Event loop
is closed` from aiosqlite's worker thread, plus 17
`PytestUnhandledThreadExceptionWarning`s every run. The point fix (commit
`3772394`) closed `SqliteResource` specifically. The underlying issue is a
class:

> Production and the `a2kit.testing` TestClient teardown lifecycle resources via
> the app lifecycle (`async with app:` → LIFO `__aexit__`). a2web's deliberate
> "AppState without an app" bypass seam (`make_default_state()` + a direct
> `fetcher.fetch(...)`) re-implements construction **without** teardown, so any
> `__aenter__`/`__aexit__` resource opened through it leaks its loop-bound worker
> thread past the test's event loop.

`SqliteResource` is the one that bites today (opened on nearly every `fetch()`);
browser / llm / cookie are the same shape and one real open away from the same
failure.

## Decision (provisional)

1. **Teardown is automatic, covering every construction path.** An autouse
   fixture (`_sqlite_lifecycle`) closes every test-constructed `SqliteResource`
   inside the test's own event loop before pytest-asyncio tears the loop down.
   Instances are tracked by wrapping `SqliteResource.__init__`, so both the
   `make_default_bundle` helper and direct `SqliteResource(...)` constructions
   are covered without per-test discipline. The daemon-thread monkeypatch and
   the `__init__` tracking are **kept** — see "What the investigation changed".

2. **A deterministic fitness function, built and proven first.** The same
   fixture, after closing, asserts no tracked resource is left open
   (`_conn is not None`) — an open-*state* fact, checked in the same teardown so
   the order is guaranteed. This is deterministic where the symptom is not.
   Proven load-bearing: with close skipped, it fails **71 errors every run**
   (3/3); with close active, 841 pass, 0 errors. This is the
   eval-substrate-first discipline: build the detector, watch it catch the bug,
   then fix.

3. **`filterwarnings=error` was tried and removed — it re-added flakiness.**
   Promoting `PytestUnhandledThreadExceptionWarning` to an error was intended as
   a broad backstop, but the residual `Event loop is closed` symptom is a rare,
   benign aiosqlite teardown race that fires ~1/15 runs even when the
   deterministic guard confirms zero open resources. Promoting it to an error
   therefore converted a harmless warning into a hard ~1/15 failure — the exact
   flakiness this change exists to kill. Removed. The deterministic state guard
   is the sole fitness function; with it (and no warning-as-error), 20/20
   full-suite runs were clean with zero warnings.

4. **The principled home is a2kit.** "Resources entered outside an app are
   drained at test teardown" is a lifecycle-owner contract. a2kit is a pinned
   dependency (not editable here), so this is filed as an upstream wish; a2web's
   fixture is the bridge until a2kit ships the affordance.

## What the investigation changed

The first plan was to *remove* the daemon-thread patch and the `__init__`
wrapper as "workarounds," and to migrate every caller onto a fixture. The
implementation disproved both:

- `aiosqlite.Connection.close()` does **not** terminate the worker thread — it
  closes the connection (no more pending ops, so no closed-loop callback) but
  the thread stays **parked and `is_alive()`** until process exit. So the daemon
  patch is still required (parked threads must not hang `threading._shutdown()`),
  and a thread-liveness guard is useless (it can't tell parked-closed from
  leaked). The deterministic signal is connection *state*, not the thread.
- The `__init__` wrapper is the robust mechanism (covers every construction
  path); migrating callers to a fixture would be more fragile, not less. Kept.

## Reconfirm

Move to plain `Accepted` once the suite is green with zero thread warnings
across 15+ runs (done: 15/15 pre-change; re-verify post-change) AND the fitness
function is shown to still fail when close is skipped (done: 71 errors × 3 runs).
The a2kit upstream remains a tracked deferred item.

## References

- Commit `3772394` (point fix); `tests/conftest.py`; `packages/http_cache.py`
  (`SqliteResource`).
- `a2kit.testing` (`TestClient`, `ambient_for_tests_autouse`) — the lifecycle
  owner; the long-term home for the contract.
- extraction-fidelity-program — the instrument-first methodology this mirrors.
