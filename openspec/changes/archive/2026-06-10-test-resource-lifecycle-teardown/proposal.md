## Why

The test suite intermittently failed (~1-in-5 to 1-in-10 runs) with
`RuntimeError: Event loop is closed` from aiosqlite's worker thread, plus 17
`PytestUnhandledThreadExceptionWarning`s every run. Root cause is a *class*, not
a single bug: a lifecycle resource (`SqliteResource`, and by shape every
`__aenter__`/`__aexit__` resource — browser, llm, cookie) opened by a test
through the deliberate "AppState without an app" bypass seam
(`make_default_state()` + direct `fetcher.fetch(...)`) is never closed, so its
loop-bound worker thread outlives the test's function-scoped event loop. The
app lifecycle (`async with app:`) and the `a2kit.testing` TestClient both drive
LIFO `__aexit__` teardown; the bypass seam re-implements construction **without**
teardown. A point fix (commit `3772394`) closes `SqliteResource` specifically;
this change closes the class and makes recurrence impossible to land silently.

## What Changes

- **Instrument first (fitness function).** Promote the leak symptom from a
  flaky warning to a deterministic, immediate failure: treat
  `PytestUnhandledThreadExceptionWarning` as an error, plus an autouse
  thread-accounting guard that fails any test which leaks a live aiosqlite /
  resource worker thread. Proven to catch the class by reverting the point fix
  and watching it fail loud.
- **Structural fix at the right layer.** Give the unit-test bypass seam the
  same teardown contract as production: `make_default_state` / `make_default_bundle`
  are superseded by a lifecycle-managed fixture that drives LIFO `__aexit__`
  teardown of every resource it built. Ad-hoc `make_default_state()` callers and
  scattered direct `SqliteResource(...)` constructions migrate onto it.
- **Remove the workarounds.** Delete the daemon-thread monkeypatch and the
  `SqliteResource.__init__` tracking wrapper from `conftest.py` — both are
  symptom-patches for the missing teardown, made redundant by the structural fix
  and guarded by the fitness function.
- **Upstream the principle (a2kit wish).** The "resources entered outside an app
  must be drained at test teardown" contract belongs to the lifecycle owner
  (a2kit). File it as feedback so `a2kit.testing` ships the affordance and no
  consumer re-implements it; a2web's fixture is the bridge until then. (a2kit is
  a pinned dependency — not editable in this repo.)

## Capabilities

### New Capabilities
- `test-resource-lifecycle`: the unit-test bypass seam ("AppState without an app")
  SHALL drive LIFO `__aexit__` teardown of every lifecycle resource it
  constructs, within the test's own event loop; and a fitness function SHALL make
  any loop-bound-resource leak fail deterministically rather than flake.

### Modified Capabilities
<!-- none — test-layout governs file placement, not execution lifecycle -->

## Impact

- `tests/conftest.py` — new lifecycle-managed fixture; removal of the
  daemon-thread monkeypatch and the `SqliteResource.__init__` wrapper.
- Test files that call `make_default_state()` / `make_default_bundle()` or
  construct `SqliteResource(...)` directly — migrate to the fixture.
- `pyproject.toml` `[tool.pytest.ini_options]` — `filterwarnings` error rule.
- New `tests/architecture/` fitness test for resource-thread leaks.
- `docs/history/A2KIT_FEEDBACK_*` — the upstream wish.
- No production (`src/`) code changes; no public API or wire change.
