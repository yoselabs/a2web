## Context

The browser tier wraps Camoufox (a Firefox fork) via Playwright's async API. When the bundled Playwright Firefox driver hits an internal error (e.g. `FFPage._onUncaughtError` dereferencing an undefined `pageError.location.url` on a JS-heavy SPA), the Node driver process writes a raw stack trace to **its inherited stderr (fd 2)** — the same fd the parent Python process owns — so it lands on the operator's terminal. a2web's Python `try/except` never sees it (it is not a Python exception; `page.goto` either hangs to budget timeout or returns thin content).

Two pre-existing facts shape this design:

1. `browser.py:191` already catches the navigation `Exception` but does `del exc` — the useful internal cause is discarded and **no** `OperatorHint` is attached. `TierResult` already carries an `operator_hint` field, and `fetcher.py:1471-1472` already appends a non-null tier hint to the response. The wiring exists; the tier just never populates it on the exception path.
2. The `browser-tier` spec already has a "Subprocess stderr lands in LDD diagnostics" requirement written for this exact TypeError — but `browser_subprocess_stderr` exists nowhere in the code, and it names the **retired** LDD substrate (a2kit v0.42 / ADR-0027 removed `a2kit.ldd`; events now emit via `await a2kit.log.info(...)`). The requirement was specced, never implemented, and is now stale.

Why it shipped unnoticed: every browser test is stubbed. `tests/conftest.py` autouse-swaps an `_UnavailableBrowserTier` into the registry, `test_browser_pool.py` stubs Camoufox entirely, and `test_browser_tier.py` stubs the pool. No test ever launches a real browser, so "the browser tier produces nothing on a real SPA" is invisible to `make check`.

## Goals / Non-Goals

**Goals:**
- No raw Node.js/driver stack trace ever reaches the operator's terminal from the browser tier.
- Captured driver stderr is routed through the current logging substrate (`await a2kit.log.info(...)`) as a structured event, replacing the LDD-era requirement.
- A swallowed browser-tier internal exception (navigation or launch) becomes a structured `OperatorHint` carrying a useful, actionable message — never silent loss.
- A reusable helper for "caught internal exception → `OperatorHint`", applied at the browser tier's catch sites.
- One opt-in real-browser check that makes "browser tier is broken" observable without slowing the default gate.

**Non-Goals:**
- No Chromium / second-engine fallback. If a second engine is ever justified it is a *new tier*, not a fallback on this one. (Explicit per the proposal.)
- No pipeline-wide sweep of every `except`-and-swallow site — browser tier only this change; the helper makes a later sweep cheap.
- No response-envelope or tool-signature change; no new top-level dependency.

## Decisions

### 1. Capture driver stderr via a `sys.stderr` fileno shim across the launch (spike-resolved)
The noisy writer is the Playwright **driver** (the `coreBundle.js` Node server), whose stderr is inherited from `sys.stderr` — not Firefox's own output, and not a Python exception. The spike (task 1) found the clean hook the design hoped for: Playwright spawns its driver with `stderr=_get_stderr_fileno()`, which reads **`sys.stderr.fileno()` at spawn time** (`playwright/_impl/_transport.py:126`). So we swap `sys.stderr` for a thin shim across the `AsyncCamoufox.__aenter__()` launch: the shim returns our pipe's write fd from `.fileno()` and delegates every other attribute (including `.write`/`.flush`/`.closed`) to the real stream. The driver subprocess inherits the pipe as its stderr for its whole life; the parent's fd 2 is **never touched**. Lines are drained on the event loop (`loop.add_reader`) and forwarded via `await a2kit.log.info(BrowserSubprocessStderr(...))`. The shim is restored immediately after launch; only the driver keeps writing to the pipe.

*Why this over the OS-level `dup2(write_end, 2)` originally floated as primary:* `dup2` is version-proof but redirects the parent's fd 2 for the whole (multi-second) launch window, so any concurrent fd-2 writer (the a2kit `stderr_sink`) is captured and re-emitted. The `sys.stderr`-fileno shim confines the redirect to the spawned child — **zero parent blast radius** — which matters more here than version-proofing, since the launch window is not instantaneous. The dependency on `_get_stderr_fileno()` reading `sys.stderr.fileno()` is the accepted trade (see Risks).

*Alternatives considered:* (a) OS-level `dup2` on fd 2 — rejected as above (wider blast radius). (b) `page.on("pageerror")` — rejected: catches page-JS errors, not the driver's own `coreBundle.js` crash. (c) Leave it and only add the hint — rejected: the terminal noise is half the reported problem.

*Boundary:* the fd mechanics live in the (domain-free) `BrowserPool`, which calls an **injected async sink**; the typed-event emission is wired on the domain side (`state._emit_browser_stderr`). The pool never imports `a2web.<domain>`, preserving packages-independence. Capture is opt-in: without a sink (test/default pools) the launch is untouched.

### 2. Internal exception → `OperatorHint` via a small helper, reusing existing wiring
Replace `del exc` at the navigation catch site with a helper, e.g. `_internal_error_hint(exc, *, code, fix) -> OperatorHint`, producing `OperatorHint(code="browser_internal_error", message=<summarized exc>, fix=<actionable>)`. Attach it to the returned `TierResult.operator_hint`; `fetcher.py:1471-1472` already surfaces it onto `operator_hints`. The launch-failure path keeps its existing `browser_unavailable` hint. `browser_internal_error` becomes a new stable `OperatorHint.code` value (documented alongside the others). The `message` is a trimmed one-line summary of the exception type + text — never a multi-line stack dump on the wire.

*Alternative considered:* a brand-new verdict for internal errors — rejected; keep `Verdict.connection_error` (existing path), the hint carries the detail. Closed-enum verdicts stay stable.

### 3. New typed event for captured driver stderr (post-LDD)
Add a `BrowserSubprocessStderr` (or similarly named) payload to `src/a2web/events/types.py`, emitted via `await a2kit.log.info(...)` with the trimmed line in its fields. This supersedes the LDD-named `browser_subprocess_stderr` `StageStarted/Ended` pair the stale requirement describes. The happy path emits zero such events (no noise when the driver is clean).

### 4. The "real check" is a deterministic local JS fixture, opt-in behind a marker
The smoke test serves a tiny **local page that renders its content via JavaScript** (offline, deterministic) and asserts the tier launches real Camoufox, executes the JS, and returns non-empty markdown. It opts out of the autouse `_UnavailableBrowserTier` stub (as `test_browser_tier.py::_restore_real_browser` already does) and is gated behind a registered `@pytest.mark.browser` marker. `make check` / default `make test` run `-m "not browser"`; a new `make test-browser` target runs it. Skipped automatically when the Camoufox binary is absent.

*Why local fixture over a live URL (Trendyol):* the specific upstream Trendyol TypeError is in Playwright's driver and is not ours to reproduce or fix. What we *can* own and regression-guard is "browser tier launches, executes JS, yields content" — the structural-broken class. A local fixture makes that deterministic and CI-capable; a live URL is geo/anti-bot flaky and tests upstream, not us. The stderr-capture path is verified separately by feeding a synthetic noisy line through the drain and asserting one event + clean terminal.

## Risks / Trade-offs

- **The shim depends on Playwright reading `sys.stderr.fileno()` at spawn** (`_get_stderr_fileno`) → confirmed against the installed version in the spike; a future Playwright change could silently re-break capture. Accepted because the blast-radius win is large and the opt-in smoke check plus the pool plumbing tests guard the mechanism; if Playwright changes the seam, fall back to the version-proof `dup2`.
- **Swapping `sys.stderr` (even briefly) could redirect a concurrent thread's own subprocess spawn** → the swap is held only across the single launch, which runs under the pool `_lock` and happens exactly once (subsequent `_ensure` calls return at the warm guard); a2web has no other concurrent driver-spawning code.
- **Real-browser smoke test is slow and needs a browser binary** → opt-in marker only, never in `make check`, auto-skip when Camoufox missing, deterministic local fixture (no network).
- **On-loop reader lifecycle (leak / dangling fd on close)** → `add_reader`/`remove_reader` paired; `close()` calls `_stop_stderr_capture()` (idempotent: removes the reader, flushes any trailing line, closes the read fd); EOF (driver exit) also tears down. No background thread.

## Migration Plan

Pure addition — no envelope or signature change, no dependency change. Land behind the same install (`[browser]` extra unchanged). Rollback = revert the change; the tier returns to its prior swallow-and-leak behavior. The `browser` pytest marker and `make test-browser` target are additive and backward compatible.

## Open Questions (resolved during apply)

- ~~Exact Camoufox/Playwright stdio seam~~ → **Resolved:** Playwright reads `sys.stderr.fileno()` at driver spawn (`_transport.py`); the fileno shim is the clean hook, chosen over the `dup2` fallback for zero parent blast radius.
- ~~Final wording of the `browser_internal_error` `fix` string~~ → **Resolved:** "transient browser-driver error — retry; if it persists the driver (Playwright/Firefox) is at fault, not the target. Set `A2WEB_BROWSER_ENABLED=false` to skip the browser tier." (retry + disable; the driver bug is upstream).
- ~~Captured-stderr event level~~ → **Resolved:** emitted at `info` (the domain sink calls `a2kit.log.info`); these are diagnostic, not alarms, and stay file-only under the CLI-quiet default level.
