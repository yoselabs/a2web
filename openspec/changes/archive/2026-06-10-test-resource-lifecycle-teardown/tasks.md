## 1. Provisional ADR

- [x] 1.1 Write `docs/adr/0008-test-resource-lifecycle-teardown.md` — provisional,
  records the class, the layer decision, instrument-first sequencing, and (added
  during impl) the "what the investigation changed" corrections.

## 2. Instrument first (fitness function) — build and PROVE it catches the class

- [x] 2.1 Evaluated `filterwarnings = ["error::pytest.PytestUnhandledThreadExceptionWarning"]`
  as a backstop and **removed it** — it converts the rare benign aiosqlite
  teardown-race warning into a ~1/15 hard failure, re-adding flakiness. A
  pyproject note records why. The deterministic state guard is the sole detector.
- [x] 2.2 Add the deterministic fitness guard. (Revised from the original
  thread-leak guard: a thread-liveness check was tried and **rejected** —
  aiosqlite parks the worker thread alive after a clean close, so liveness can't
  distinguish parked-closed from leaked. The guard asserts open *state*
  `_conn is not None` at teardown instead.) Lives in the `_sqlite_lifecycle`
  autouse fixture in `tests/conftest.py`.
- [x] 2.3 PROVE the instrument: env toggle `A2WEB_PROOF_SKIP_SQLITE_CLOSE=1`
  skips the close. Confirmed **71 errors on every run (3/3)** — deterministic —
  vs `841 passed, 0 errors` with close active.

## 3. Structural fix — close in-loop, every construction path

- [x] 3.1 `_sqlite_lifecycle` autouse async fixture: closes every tracked
  `SqliteResource` in the test's event loop, then asserts none left open, then
  clears the registry. One fixture so close-then-assert order is guaranteed
  (a separate sync guard + async close finalize in an unreliable order under
  pytest-asyncio).
- [x] 3.2 Keep the `SqliteResource.__init__` tracking wrapper — it is the robust
  all-construction-paths mechanism (covers `make_default_bundle` and direct
  `SqliteResource(...)`), not a hack to migrate away from.
- [x] 3.3 Keep the daemon-thread monkeypatch — required: `close()` parks the
  worker thread (it dies at process exit), so without daemon a parked thread
  would hang `threading._shutdown()`. (Original "remove it" task disproven; see
  ADR "What the investigation changed".)

## 4. Validate

- [x] 4.1 `make check` green (841 passed, 90% cov, arch ok).
- [x] 4.2 Stress: 20/20 consecutive full-suite runs clean, 0 failures, 0 thread
  warnings.

## 5. Upstream the principle (a2kit wish)

- [x] 5.1 Wrote `docs/history/A2KIT_FEEDBACK_v0.42.md` (round 13): `a2kit.testing`
  should own "resources entered outside an app are drained at test teardown", so
  no consumer re-implements the tracking + in-loop close + leak guard.

## 6. Reconfirm the ADR

- [x] 6.1 Moved ADR-0008 to plain `Accepted` (confirmed 2026-06-10); a2kit wish
  (`A2KIT_FEEDBACK_v0.42.md`) noted as the deferred long-term home.
