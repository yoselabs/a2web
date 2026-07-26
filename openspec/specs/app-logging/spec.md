# app-logging Specification

## Purpose
The single managed logging surface for a2web: every operational and diagnostic
event flows through one process-wide `a2web` logger (typed payloads on stdlib
logging, owned by `src/a2web/log.py`), never through a bypassing channel and never
to `stdout` under MCP stdio.
## Requirements
### Requirement: Single managed logging channel

All a2web operational and diagnostic logging SHALL flow through the single process-wide `a2web` logger, owned by `src/a2web/log.py` (`propagate=False` + a `NullHandler` floor). a2web SHALL NOT emit logs through an unconfigured `structlog` logger or any logger that bypasses the `a2web` logger. Because there is exactly one channel, suppressing the `a2web` logger (raising its level or disabling it) SHALL mute every a2web log path.

#### Scenario: No rogue structlog loggers in source

- **WHEN** an architecture test walks every `.py` file under `src/a2web/`
- **THEN** no module calls `structlog.get_logger(...)` (or otherwise instantiates a structlog logger) as an emit channel

#### Scenario: a2web logs obey the kill switch

- **WHEN** the `a2web` logger is suppressed (level raised above the emitted level, or disabled) and a2web exercises a code path that previously emitted a `structlog` line (e.g. an unavailable provider)
- **THEN** no a2web log line is written to stdout or stderr

### Requirement: Logs never reach stdout in MCP stdio mode

a2web SHALL NOT write log lines to `stdout`. In MCP stdio transport, `stdout` is reserved for the JSON-RPC protocol stream; operational logs SHALL travel on the MCP log wire (the in-flight FastMCP context forward) or a configured stderr/file handler only. The `a2web` logger's `propagate=False` + `NullHandler` floor exist precisely so a stray record cannot reach the root logger's default stderr writer and interleave with the protocol stream.

#### Scenario: stdout stays clean while logging fires

- **WHEN** a code path that emits an a2web log record runs under default configuration
- **THEN** the record is delivered to the `a2web` logger's handlers (stderr / wire / file per configuration) and `stdout` receives nothing from the logging subsystem

### Requirement: CLI is quiet by default

In CLI mode, a2web SHALL produce no log output for routine operation. Log lines SHALL surface only when a problem or exceptional condition is logged at `warning` or above, or when the operator opts in by lowering the `a2web` logger's level and/or attaching a verbose stderr handler.

#### Scenario: Successful CLI fetch emits no diagnostic noise

- **WHEN** `a2web web query` completes a fetch successfully under default logging configuration
- **THEN** no `info`/`debug` diagnostic lines (e.g. provider fallback notices) are printed to the terminal

### Requirement: Severity altitude — resolved is silent, no-provider is an operator hint

Diagnostics SHALL be emitted at a severity matching operator value. A successful resolution that merely skipped a fallback SHALL NOT emit at `info` or above. When LLM extraction cannot run because no provider resolved, the condition SHALL surface to the caller as an `OperatorHint` on the response (the user-facing "info link" mechanism) carrying an actionable message, rather than as a log-channel `warning`. The `query` tool SHALL NOT fail the whole call solely because no LLM provider is available.

#### Scenario: Provider fallback miss is silent on the happy path

- **WHEN** provider selection resolves a usable provider (e.g. `claude-code`) after a non-selected candidate (e.g. `anthropic`) was unavailable
- **THEN** the unavailable-candidate fact is emitted at `debug` only (below the `a2web` logger's default MCP-wire threshold of `info`, so it is not streamed on the wire), and no `info` line claims unavailability

#### Scenario: No provider available surfaces an actionable hint

- **WHEN** provider selection exhausts every candidate and resolves no usable LLM provider during a `query`
- **THEN** the response carries an `OperatorHint` whose message names the actionable remedy (e.g. set the API-key env var or log into Claude Code), and the call does not raise solely for the missing provider

### Requirement: No retired "LDD" terminology in live code

a2web live source SHALL refer to the logging substrate as plain logging on the `a2web` channel — a2web owns the logger (`src/a2web/log.py`), it is not managed by any framework. The retired "LDD" branding (the `a2kit.ldd` module, removed in a2kit v0.42 / ADR-0027, and a2kit itself retired in the 2026-07-22 sunset) SHALL NOT appear in `src/a2web/` comments, docstrings, or identifiers. `CLAUDE.md` SHALL likewise drop the LDD *branding* of a2web's logging; factual references that name a2kit's removed `a2kit.ldd` API (migration-history pointers and never-use guards) MAY remain, since they reinforce that the subsystem is gone. Dated historical records under `docs/history/` are exempt. The underlying typed-event functionality (events emitted via `await a2web.log.info(...)`, sinks as `logging.Handler`s) is retained unchanged.

#### Scenario: No LDD references in live source

- **WHEN** a case-insensitive search for the token `ldd` runs over `src/a2web/**.py`
- **THEN** no matches remain (identifiers, comments, or docstrings), excepting incidental substrings of unrelated words

### Requirement: Freeform emit ergonomics preserved

a2web log sites SHALL retain string-message-plus-structured-fields ergonomics on the `a2web` logger. Async call sites SHALL emit via `await a2web.log.{debug,info,warning,error}("event", **fields)` (from `src/a2web/log.py`), which emits one stdlib record and, under an active tool call, forwards it on the MCP wire. Synchronous boot/pure-function call sites SHALL emit via the sync helpers `log_debug`/`log_info`/`log_warning`/`log_error` on the same `a2web` logger, carrying the same structured-fields payload with no `await` and no event loop.

#### Scenario: Async site emits structured fields on the wire

- **WHEN** an async code path emits `await a2web.log.warning("eval_system_failed", slug=..., system=..., error=...)` inside an active tool call scope
- **THEN** the record carries the named fields and is forwarded on the MCP wire at `warning`

#### Scenario: Sync boot site emits without an event loop

- **WHEN** a synchronous registry/boot function (no running call scope) logs an event via the sync helper (e.g. `log_info("event", **fields)`)
- **THEN** the record reaches the configured `a2web` logger handlers with its structured fields, and no `await`/event-loop is required

