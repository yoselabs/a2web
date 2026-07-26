## MODIFIED Requirements

### Requirement: Browser driver subprocess stderr is captured, not leaked

The browser tier SHALL capture stderr emitted by Camoufox's underlying Playwright Node.js driver process so that no driver/JS stack trace reaches the operator's terminal. The tier SHALL NOT let the driver subprocess inherit the Python parent's stderr (fd 2) uncaptured. Each non-empty captured line SHALL be routed through the current logging substrate via `await a2web.log.info(...)` as a typed event (defined in `src/a2web/events/types.py`), carrying the trimmed line in its fields. When the driver emits an internal error (e.g. the `FFPage._onUncaughtError` TypeError seen on JS-heavy SPAs), the captured trace SHALL appear only in the logging substrate and the operator's terminal SHALL see no raw Node.js output. A clean render SHALL emit zero such events.

#### Scenario: Driver internal error is captured, not leaked to the terminal

- **WHEN** the Playwright Firefox driver writes an internal stack trace to its stderr during a browser fetch (e.g. the `coreBundle.js` `pageError.location.url` TypeError)
- **THEN** the trace is captured and emitted as one or more typed log events via `a2web.log.info`, and no raw Node.js stack trace appears on the operator's terminal

#### Scenario: Clean browser fetch emits no stderr events

- **WHEN** the browser tier successfully renders a page and the driver writes nothing to stderr
- **THEN** zero subprocess-stderr log events are emitted (no noise on the happy path)
