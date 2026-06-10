## ADDED Requirements

### Requirement: every test-constructed loop-bound resource is closed in-loop

The test harness SHALL automatically close every `SqliteResource` constructed during a test, within that test's own event loop, before the loop is torn down — regardless of construction path (the `make_default_bundle` helper or a direct `SqliteResource(...)`). Teardown SHALL be automatic (autouse) so an individual test cannot forget it; it does not require the test to use a particular builder. `SqliteResource` is the only resource holding a loop-bound worker thread that unit tests open today; a future loop-bound resource is covered by the backstop in the second requirement.

#### Scenario: a direct fetch test leaks no worker thread

- **WHEN** a test builds state via the bypass seam and calls `fetcher.fetch(...)`,
  causing the cache `SqliteResource` to open its aiosqlite connection
- **THEN** the resource is closed within the test's event loop on fixture
  teardown, and no aiosqlite worker thread survives into the next test

#### Scenario: teardown is a no-op when a resource was never opened

- **WHEN** a test constructs a lifecycle resource but never enters it (no
  connection / thread is created)
- **THEN** teardown completes without error and without forcing the resource open

#### Scenario: teardown closes every tracked instance regardless of how built

- **WHEN** a test constructs multiple `SqliteResource`s — some via
  `make_default_bundle`, some directly — and opens them
- **THEN** every one is closed on teardown within the test's event loop, so none
  is left open into the next test

### Requirement: a resource left open is a deterministic failure

The test harness SHALL fail deterministically when a test leaves a `SqliteResource`
open (its connection still non-null) past the test's event loop. The detector
SHALL be a state assertion at teardown — open vs closed is a fact — and SHALL
NOT rely on the timing-dependent `RuntimeError: Event loop is closed` symptom,
which fires only when the worker thread is mid-operation at teardown and
therefore flakes. (Promoting `PytestUnhandledThreadExceptionWarning` to an error
was evaluated and rejected: it converted that rare benign symptom into a ~1/15
hard failure, re-introducing the flakiness this change removes.) The
daemon-thread treatment of the worker thread is retained (it prevents a parked
thread from hanging process exit) and is orthogonal to leak detection.

#### Scenario: a reintroduced leak fails the suite deterministically

- **WHEN** the in-loop close is skipped so resources are left open, and the full
  suite is run repeatedly
- **THEN** the state-assertion fitness function fails the same leaking tests on
  every run (deterministic), naming each offender — not intermittently

#### Scenario: a clean suite leaves no resource open

- **WHEN** the full suite runs with teardown in place
- **THEN** no test leaves a `SqliteResource` open at teardown, and no
  `PytestUnhandledThreadExceptionWarning` / `Event loop is closed` event occurs
