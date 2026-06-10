# a2kit feedback — round 13 (2026-06-10)

Outgoing wish for the next a2kit minor. Captured from a2web's
`test-resource-lifecycle-teardown` change (ADR-0008). Not in scope for that
change itself — it is an upstream framework ask.

## Drain resources entered outside an app at test teardown

**Ask.** `a2kit.testing` should own teardown of lifecycle resources that a test
constructs **without** going through `async with app:` / the TestClient. Either
a context-managed test-state builder (`async with a2kit.testing.resources(...)
as state:` that enters lazily and unwinds `__aexit__` LIFO), or have the
existing autouse `ambient_for_tests_autouse` track resources entered during the
test and close them in the test's event loop on teardown.

**Why.** a2kit owns the resource lifecycle protocol (`__aenter__`/`__aexit__`,
`app.provide`, `async with app:`). Production and the TestClient drive teardown
through that lifecycle. But a2kit also blesses a bypass seam — tests that build
state directly and call a tool function — and there is **no** affordance to
teardown the resources that seam opens. A resource with a loop-bound background
thread (e.g. a `SqliteResource` over aiosqlite) opened by such a test and never
closed leaves its worker thread alive past the test's function-scoped event
loop; when the loop closes, the thread's next `call_soon_threadsafe(...)` raises
`RuntimeError: Event loop is closed`, surfaced as a
`PytestUnhandledThreadExceptionWarning` and, under coverage / unlucky timing, an
intermittent hard failure attributed to an unrelated test. This is a
test-isolation contract — "a resource entered outside an app is drained before
the loop closes" — and it belongs to the lifecycle owner, not to each
consumer's conftest.

**a2web's workaround (the bridge).** `tests/conftest.py` wraps
`SqliteResource.__init__` to track every instance (covering both the
`make_default_bundle` helper and direct `SqliteResource(...)`), and an autouse
async fixture (`_sqlite_lifecycle`) closes each in the test's loop on teardown,
then asserts none was left open (a deterministic state-based fitness function;
`filterwarnings=error::PytestUnhandledThreadExceptionWarning` is a sound but
flaky backstop). It works, but it is per-resource-type, reaches into
`SqliteResource._conn`, and must be re-implemented by every a2kit consumer that
uses the bypass seam.

**Notes for the a2kit side.**
- `aiosqlite.Connection.close()` does not terminate the worker thread — it
  parks alive until process exit — so a2kit's helper should also keep the
  daemon-thread treatment (or document that consumers must), and detection must
  be state-based, not thread-liveness-based.
- The affordance should be a no-op for resources never entered (cheap for sync
  tests / unopened resources).
