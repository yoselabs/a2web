## REMOVED Requirements

### Requirement: NDJSON writer with lazy open

**Reason:** Replaced by stdlib `logging.handlers.RotatingFileHandler` plus structlog `JSONRenderer` plus a small gzip rotator callback. ~250 LOC of hand-rolled writer / lock / rotation logic is replaced by ~20 LOC of stdlib glue.

**Migration:** Delete `src/a2web/log/writer.py`. The new module exposes a `build_log_handler(settings: AppSettings) -> logging.Handler` factory that returns a configured `RotatingFileHandler` with `rotator` set to a callback that gzips the rolled file. `state.log_writer` becomes a thin wrapper that formats a `LogRecord` to JSON via structlog and writes through the handler.

### Requirement: Size-based rotation with gzip on rollover

**Reason:** Same as above — stdlib `RotatingFileHandler` does size-based rotation; the `rotator` callback does the gzip step.

**Migration:** Configure the handler with `maxBytes=16 * 1024 * 1024` (16 MiB) and `backupCount=20`. The `rotator=gzip_rotator` callback renames the rolled file with `.gz` suffix and gzips its contents via `gzip.open(...)` + `shutil.copyfileobj`. The active file name remains `fetches-YYYY-MM-DD.ndjson`; rolled files become `fetches-YYYY-MM-DD-NN.ndjson.gz`.

## MODIFIED Requirements

### Requirement: LogRecord schema

The system SHALL define `LogRecord` in `src/a2web/log/record.py` as `@dataclass(slots=True)` at module scope. Field set unchanged from v0.1.0. Serialization SHALL be via structlog's `JSONRenderer` (or a thin `record_to_json` helper that produces stable key order) rather than custom JSON encoding.

#### Scenario: LogRecord at module scope, slots-enabled

- **WHEN** static analysis walks `a2web.log.record`
- **THEN** `LogRecord` is a `@dataclass(slots=True)`, importable as `from a2web.log.record import LogRecord`

#### Scenario: JSON serialization stable

- **WHEN** the same `LogRecord` is serialized twice
- **THEN** the resulting NDJSON lines are byte-identical (key order preserved)

### Requirement: Best-effort writes

The system SHALL NOT fail a fetch because of a log write error. The new stdlib-handler-based writer SHALL be wrapped such that any exception during `handler.emit(...)` is caught at the orchestrator boundary; the orchestrator SHALL append `OperatorHint(code="log_write_failed", message=str(exc))` to the response, route a WARNING through structlog, and return the `FetchResponse` as if the log had succeeded.

#### Scenario: Permission error on write does not propagate

- **WHEN** the handler is configured against a read-only directory and a fetch runs
- **THEN** the fetch returns a populated `FetchResponse` with `operator_hints` containing one entry whose `code == "log_write_failed"`, and the response status reflects the fetch outcome (not the log failure)

### Requirement: Opt-out via settings

`AppSettings.log_enabled: bool = True` is preserved. When `False`, the log writer wrapper SHALL be a no-op that returns without invoking the handler (or, equivalently, a `NullHandler` is configured).

#### Scenario: Disabled writer never touches the filesystem

- **WHEN** `A2WEB_LOG_ENABLED=false` is exported, the App is constructed, and a fetch runs
- **THEN** no files are created under the log directory

## ADDED Requirements

### Requirement: stdlib RotatingFileHandler integration

The system SHALL provide `build_log_handler(settings: AppSettings) -> logging.Handler` in `src/a2web/log/writer.py`. The handler SHALL be a `logging.handlers.RotatingFileHandler` configured with:

- `filename`: resolved via `log_path()` (preserved from v0.1.0 — `$A2WEB_LOG_DIR` or `~/.a2web/logs/fetches-YYYY-MM-DD.ndjson`)
- `maxBytes`: 16 MiB
- `backupCount`: 20
- `rotator`: a gzip callback that renames the rolled file with `.gz` and writes gzipped content

The handler SHALL use structlog's `JSONRenderer` (or a compatible formatter) to produce one NDJSON record per emit.

#### Scenario: Rotation crosses threshold

- **WHEN** the active file size after a write exceeds `maxBytes`
- **THEN** the file is renamed to `fetches-YYYY-MM-DD-1.ndjson`, then gzipped to `fetches-YYYY-MM-DD-1.ndjson.gz`, and a new active file is opened on the next write

#### Scenario: backupCount enforced

- **WHEN** rotations exceed 20 in a single time period
- **THEN** the oldest rolled `.gz` files are deleted by the stdlib handler's backup-count discipline
