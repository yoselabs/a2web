## REMOVED Requirements

### Requirement: Subprocess stderr from camoufox/playwright lands in LDD diagnostics

**Reason**: Names the retired LDD substrate (a2kit v0.42 / ADR-0027 removed `a2kit.ldd`; events now emit via `await a2kit.log.info(...)`), and was never implemented (`browser_subprocess_stderr` appears nowhere in the code). Replaced by the correctly-substrated requirement below.

**Migration**: None required in production — the behavior never shipped. Superseded by "Browser driver subprocess stderr is captured, not leaked".

## ADDED Requirements

### Requirement: Browser driver subprocess stderr is captured, not leaked

The browser tier SHALL capture stderr emitted by Camoufox's underlying Playwright Node.js driver process so that no driver/JS stack trace reaches the operator's terminal. The tier SHALL NOT let the driver subprocess inherit the Python parent's stderr (fd 2) uncaptured. Each non-empty captured line SHALL be routed through the current logging substrate via `await a2kit.log.info(...)` as a typed event (defined in `src/a2web/events/types.py`), carrying the trimmed line in its fields. When the driver emits an internal error (e.g. the `FFPage._onUncaughtError` TypeError seen on JS-heavy SPAs), the captured trace SHALL appear only in the logging substrate and the operator's terminal SHALL see no raw Node.js output. A clean render SHALL emit zero such events.

#### Scenario: Driver internal error is captured, not leaked to the terminal

- **WHEN** the Playwright Firefox driver writes an internal stack trace to its stderr during a browser fetch (e.g. the `coreBundle.js` `pageError.location.url` TypeError)
- **THEN** the trace is captured and emitted as one or more typed log events via `a2kit.log.info`, and no raw Node.js stack trace appears on the operator's terminal

#### Scenario: Clean browser fetch emits no stderr events

- **WHEN** the browser tier successfully renders a page and the driver writes nothing to stderr
- **THEN** zero subprocess-stderr log events are emitted (no noise on the happy path)

### Requirement: Browser tier surfaces internal driver errors as an OperatorHint

When `BrowserTier.fetch` catches an internal exception on the navigation path (network reset, driver error, or other non-timeout failure during `page.goto` / content capture), the tier SHALL NOT discard the exception. It SHALL attach an `OperatorHint` to the returned `TierResult.operator_hint` with a stable `code == "browser_internal_error"`, a `message` that is a single-line summary of the exception type and text (never a multi-line stack dump), and a non-null actionable `fix`. The verdict SHALL remain `Verdict.connection_error` (the existing path). The orchestrator's existing tier-hint surfacing SHALL carry the hint onto the response `operator_hints`.

#### Scenario: Navigation exception produces a structured hint instead of silent loss

- **WHEN** `page.goto` raises a non-timeout exception inside `BrowserTier.fetch`
- **THEN** the result has `verdict == Verdict.connection_error` and a populated `operator_hint` with `code == "browser_internal_error"`, a one-line `message`, and a non-null `fix`

#### Scenario: Internal-error hint reaches the response

- **WHEN** the orchestrator dispatches the browser tier and the tier returns a `browser_internal_error` hint
- **THEN** that hint appears in the response `operator_hints` list

#### Scenario: Hint message carries no multi-line stack dump

- **WHEN** the caught exception's string representation spans multiple lines
- **THEN** the `OperatorHint.message` is a single trimmed line (the multi-line detail belongs in the captured-stderr log events, not the wire hint)

### Requirement: Browser tier has an opt-in real-browser smoke check

The test suite SHALL include a real-browser smoke check that launches the actual Camoufox binary (opting out of the autouse `_UnavailableBrowserTier` stub), navigates a deterministic local JavaScript-rendering fixture, and asserts the tier returns non-empty rendered markdown with `js_executed == True`. The check SHALL be gated behind a registered pytest marker (`browser`) and SHALL be excluded from the default `make check` / `make test` run (`-m "not browser"`). It SHALL auto-skip when the Camoufox binary is unavailable. A dedicated `make` target SHALL run it on demand.

#### Scenario: Smoke check is excluded from the default gate

- **WHEN** `make check` runs
- **THEN** the real-browser smoke check is deselected (the marker is excluded) and no Camoufox process launches during the default gate

#### Scenario: Smoke check verifies real JS execution on demand

- **WHEN** the `browser`-marked smoke check runs against the local JS-rendering fixture with Camoufox installed
- **THEN** it launches a real browser, executes the fixture's JavaScript, and asserts `verdict == Verdict.ok` with non-empty `pre_rendered.content_md` and `js_executed == True`

#### Scenario: Smoke check skips when Camoufox is absent

- **WHEN** the `browser`-marked smoke check runs in an environment without the Camoufox binary
- **THEN** the check is skipped (not failed)
