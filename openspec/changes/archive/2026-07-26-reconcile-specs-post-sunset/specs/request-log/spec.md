## MODIFIED Requirements

### Requirement: Best-effort writes

The system SHALL NOT fail a fetch because of a log write error. If `write_record` raises (disk full, permissions, fd exhaustion), the orchestrator SHALL catch the exception, append an `OperatorHint(code="log_write_failed", message=...)` to the response, emit a WARNING via `a2web.log` (the single `a2web` logger, `src/a2web/log.py` — never a bypassing `structlog` logger), and return the `FetchResponse` as if the log had succeeded.

#### Scenario: Permission error on write does not propagate

- **WHEN** the writer is configured against a read-only directory and a fetch runs
- **THEN** the fetch returns a populated `FetchResponse` with `operator_hints` containing one entry whose `code == "log_write_failed"`, and the response status reflects the fetch outcome (not the log failure)
