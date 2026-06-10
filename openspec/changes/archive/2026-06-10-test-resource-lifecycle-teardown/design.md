## Context

Production and the `a2kit.testing` TestClient both teardown lifecycle resources
via the app lifecycle: `async with app:` enters resources lazily and unwinds
them LIFO through `__aexit__`. a2web deliberately keeps a second seam — "AppState
without an app" (`make_default_state()` + a direct `fetcher.fetch(...)` call) —
so unit tests can drive the orchestrator without standing up the DI container.
That seam constructs resources but **owns no teardown**. The cache
`SqliteResource` is opened on nearly every `fetch()` (cache check/write); its
aiosqlite worker thread is bound to the test's function-scoped event loop. When
the loop closes with the connection still open, the thread's next
`call_soon_threadsafe(...)` raises `RuntimeError: Event loop is closed`, surfaced
as `PytestUnhandledThreadExceptionWarning` (17/run) and — under coverage or
unlucky timing — an intermittent hard failure pinned to whichever test was
running. Commit `3772394` closes `SqliteResource` specifically via a conftest
`__init__` wrapper + autouse async fixture; this change generalizes that to the
class and removes the workarounds.

The class: **the app/TestClient own resource teardown; the bypass seam
re-implements construction without it.** Any `__aenter__`/`__aexit__` resource
opened through the seam is exposed — sqlite today, browser/llm/cookie the moment
a test opens one for real.

## Goals / Non-Goals

**Goals:**
- The bypass seam has the same teardown contract as `async with app:` (LIFO
  `__aexit__`, in the test's loop), automatic and un-forgettable.
- A fitness function turns the whole leak class from a flaky warning into a
  deterministic, attributable failure — built and proven *first*.
- Remove the daemon-thread monkeypatch and the `SqliteResource.__init__` wrapper.
- The principled home (framework-owned teardown) is filed upstream to a2kit.

**Non-Goals:**
- No production (`src/`) change; no public API / wire change.
- Not removing the bypass seam itself — it stays; it just gains teardown.
- Not editing a2kit in-repo (pinned dependency); the framework fix is a wish.
- Not converting every test to the TestClient — that is a larger migration and
  the bypass seam is intentionally supported.

## Decisions

1. **Instrument first.** Land the fitness function before the structural fix:
   `filterwarnings = ["error::pytest.PytestUnhandledThreadExceptionWarning"]`
   plus an autouse guard that snapshots aiosqlite/worker threads per test and
   fails on a leak. Validate by reverting the point fix and confirming the run
   fails *deterministically* (the instrument catches the class, not just the
   symptom). This mirrors the extraction-fidelity-program discipline: build the
   detector, watch it catch the bug, then fix.

2. **Seam becomes lifecycle-managed.** Replace the imperative
   `make_default_state()` / `make_default_bundle()` usage with an async fixture
   (e.g. `default_state` / `default_bundle`) that builds the bundle and, on
   teardown, drives LIFO `__aexit__` over every constructed resource in the
   test's event loop. `close()` is idempotent and a no-op when a resource was
   never opened, so sync tests and unopened resources pay nothing. The
   construction logic stays the single `bootstrap_state`-aligned source of truth;
   only ownership of teardown moves into the fixture.

3. **Cover direct constructions.** Tests that build `SqliteResource(...)`
   directly (notably the cookie/cache suites) migrate to the fixture or to an
   `async with` block. A thread-leak fitness guard makes any straggler fail loud
   rather than silently leak, so migration is enforced, not hoped-for.

4. **Delete the workarounds.** Once teardown is owned by the seam and guarded by
   the fitness function, remove the daemon-thread patch and the
   `SqliteResource.__init__` tracking wrapper. They masked the symptom; keeping
   them would hide a future regression from the very guard we are adding.

5. **Upstream to a2kit.** The contract "resources entered outside an app are
   drained at test teardown" belongs to the lifecycle owner. File a
   `docs/history/A2KIT_FEEDBACK_*` wish proposing `a2kit.testing` ship the
   affordance (a context-managed test-state builder, or `ambient_for_tests_autouse`
   draining entered resources). a2web's fixture is the bridge; the ADR records
   a2kit as the long-term home.

## Risks / Trade-offs

- **`filterwarnings=error` over-broad.** Scoped to
  `PytestUnhandledThreadExceptionWarning` only, not a blanket `error`, so it does
  not promote unrelated deprecation warnings. A genuinely-benign thread exception
  would now fail — acceptable: thread exceptions in this suite are not benign.
- **Failure attribution is approximate.** A leaked thread fires during whatever
  test runs next, so the guard points *near*, not exactly at, the offending test.
  The thread-accounting guard (per-test snapshot) narrows this to the leaking
  test; the warning-as-error is the backstop.
- **Migration churn.** Several suites construct `SqliteResource(...)` directly;
  migrating them is mechanical but touches multiple files. The fitness function
  makes any missed site fail loudly, bounding the risk.
- **a2kit lag.** The principled fix lands on a2kit's release cadence; until then
  a2web carries the fixture. Tracked via the provisional ADR's reconfirm task.
