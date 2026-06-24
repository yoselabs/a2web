## ADDED Requirements

### Requirement: Single managed logging channel

All a2web operational and diagnostic logging SHALL flow through the a2kit-managed `a2kit` logger tree, governed by a2kit's `LogConfig`. a2web SHALL NOT emit logs through an unconfigured `structlog` logger or any logger that bypasses `LogConfig` (level, `wire_level`, `stderr_sink`, `enabled`).

#### Scenario: No rogue structlog loggers in source

- **WHEN** an architecture test walks every `.py` file under `src/a2web/`
- **THEN** no module calls `structlog.get_logger(...)` (or otherwise instantiates a structlog logger) as an emit channel

#### Scenario: a2web logs obey the kill switch

- **WHEN** a2web runs with `A2KIT_LOG__ENABLED=false` and exercises a code path that previously emitted a `structlog` line (e.g. an unavailable provider)
- **THEN** no a2web log line is written to stdout or stderr

### Requirement: Logs never reach stdout in MCP stdio mode

a2web SHALL NOT write log lines to `stdout`. In MCP stdio transport, `stdout` is reserved for the JSON-RPC protocol stream; operational logs SHALL travel on the MCP log wire or the configured stderr handler only.

#### Scenario: stdout stays clean while logging fires

- **WHEN** a code path that emits an a2web log record runs under default configuration
- **THEN** the record is delivered to the `a2kit` logger handlers (stderr / wire / file per config) and `stdout` receives nothing from the logging subsystem

### Requirement: CLI is quiet by default

In CLI mode, a2web SHALL produce no log output for routine operation. Log lines SHALL surface only when a problem or exceptional condition is logged at `warning` or above, or when the operator opts in via `LogConfig` (e.g. `A2KIT_LOG__STDERR_SINK=pretty`, `A2KIT_LOG__WIRE_LEVEL=debug`).

#### Scenario: Successful CLI fetch emits no diagnostic noise

- **WHEN** `a2web web ask` completes a fetch successfully under default logging configuration
- **THEN** no `info`/`debug` diagnostic lines (e.g. provider fallback notices) are printed to the terminal

### Requirement: Severity altitude — resolved is silent, no-provider is an operator hint

Diagnostics SHALL be emitted at a severity matching operator value. A successful resolution that merely skipped a fallback SHALL NOT emit at `info` or above. When LLM extraction cannot run because no provider resolved, the condition SHALL surface to the caller as an `OperatorHint` on the response (the user-facing "info link" mechanism) carrying an actionable message, rather than as a log-channel `warning`. The `ask` tool SHALL NOT fail the whole call solely because no LLM provider is available.

#### Scenario: Provider fallback miss is silent on the happy path

- **WHEN** provider selection resolves a usable provider (e.g. `claude-code`) after a non-selected candidate (e.g. `anthropic`) was unavailable
- **THEN** the unavailable-candidate fact is emitted at `debug` only (not streamed on the wire or stderr at default `wire_level`), and no `info` line claims unavailability

#### Scenario: No provider available surfaces an actionable hint

- **WHEN** provider selection exhausts every candidate and resolves no usable LLM provider during an `ask`
- **THEN** the response carries an `OperatorHint` whose message names the actionable remedy (e.g. set the API-key env var or log into Claude Code), and the call does not raise solely for the missing provider

### Requirement: No retired "LDD" terminology in live code

a2web live source SHALL refer to the logging substrate as plain logging (the `a2kit` channel). The retired "LDD" branding (the `a2kit.ldd` module was removed in a2kit v0.42 / ADR-0027) SHALL NOT appear in `src/a2web/` comments, docstrings, or identifiers. `CLAUDE.md` SHALL likewise drop the LDD *branding* of a2web's logging; factual references that name a2kit's removed `a2kit.ldd` API (migration-history pointers and never-use guards) MAY remain, since they reinforce that the subsystem is gone. Dated historical records under `docs/history/` are exempt. The underlying typed-event functionality (events emitted via `a2kit.log`, sinks as `logging.Handler`s) is retained unchanged.

#### Scenario: No LDD references in live source

- **WHEN** a case-insensitive search for the token `ldd` runs over `src/a2web/**.py`
- **THEN** no matches remain (identifiers, comments, or docstrings), excepting incidental substrings of unrelated words

### Requirement: Freeform emit ergonomics preserved

a2web log sites SHALL retain string-message-plus-structured-fields ergonomics. Async call sites SHALL emit via `await a2kit.log.{debug,info,warning,error}("event", **fields)`. Synchronous boot/pure-function call sites SHALL emit via the stdlib half on the `a2kit` logger (`logging.getLogger("a2kit").{...}("event", extra={"a2kit_fields": {...}})`), exposed through a small `a2web` sync helper.

#### Scenario: Async site emits structured fields on the wire

- **WHEN** an async code path emits `await a2kit.log.warning("eval_system_failed", slug=..., system=..., error=...)` inside an active tool call scope
- **THEN** the record carries the named fields and is forwarded on the MCP wire at `warning`

#### Scenario: Sync boot site emits without an event loop

- **WHEN** a synchronous registry/boot function (no running call scope) logs an event via the sync helper
- **THEN** the record reaches the configured `a2kit` logger handlers with its structured fields, and no `await`/event-loop is required
