## REMOVED Requirements

### Requirement: LogRecord schema

**Reason**: `LogRecord` (`src/a2web/log/record.py`) was deleted by commit
`9140fc5` ("nuke NDJSON fetch log — cache covers replay"). The structured
per-step data it duplicated already ships in the response envelope's
`diagnostics` array.

**Migration**: None — the replay/inspection use case is covered by the cache
(hit-keyed lookup) and the in-envelope `diagnostics`. No consumer reads a
`LogRecord`.

### Requirement: NDJSON writer with lazy open

**Reason**: `LogWriter` (`src/a2web/log/writer.py`) and its
`write_record`/`register_state`-constructed lifecycle were deleted by `9140fc5`.
No NDJSON writer exists in `src/a2web/`.

**Migration**: None — there is no fetch-log file to write. Diagnostics live in
the response; operational logging goes through the single `a2web` logger
(`app-logging`).

### Requirement: Size-based rotation with gzip on rollover

**Reason**: The rotation/gzip machinery belonged to the deleted `LogWriter`
(`9140fc5`). With no log file, there is nothing to rotate.

**Migration**: None.

### Requirement: Log path resolution

**Reason**: `src/a2web/log/paths.py` (`$A2WEB_LOG_DIR` / `~/.a2web/logs/`
resolution) was deleted with the NDJSON layer (`9140fc5`). No code resolves a
fetch-log directory.

**Migration**: None. The sqlite cache path (which does persist) is owned by the
`container-image` capability, not here.

### Requirement: Best-effort writes

**Reason**: The write-and-handle block in `fetcher.fetch()` (catch a log-write
error, append a `log_write_failed` `OperatorHint`, continue) was deleted by
`9140fc5` along with the writer it guarded. There is no log write that can fail.

**Migration**: None — no `log_write_failed` hint is emitted because no fetch log
is written.

### Requirement: Opt-out via settings

**Reason**: The `log_enabled` opt-out described here assigned a no-op
`LogWriter` to `state.log_writer` via the a2kit `register_state` path — all
deleted by `9140fc5`. (`log_enabled` was later re-added for a different
subsystem: it governs the single `a2web` logger.)

**Migration**: The surviving `log_enabled` behaviour — suppressing all a2web
logging — is owned by the `app-logging` requirement "Single managed logging
channel" (the single-mute-point scenario).
