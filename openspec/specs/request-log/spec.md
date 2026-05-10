# request-log Specification

## Purpose
TBD - created by archiving change pr4-ndjson-log. Update Purpose after archive.
## Requirements
### Requirement: LogRecord schema

The system SHALL define `LogRecord` in `src/a2web/log/record.py` as `@dataclass(slots=True)` at module scope. The dataclass SHALL carry: `ts: str` (ISO 8601 UTC, ms precision), `url: str`, `final_url: str`, `host: str`, `tier: str`, `status: str` (closed enum FetchStatus), `verdict: str` (closed enum Verdict, dominant value across diagnostics), `cache: str` (closed enum CacheState), `total_ms: int`, `content_chars: int`, `diagnostics: list[dict]` (compact per-step rows), `title: str | None`, `error: str | None`.

#### Scenario: LogRecord at module scope, slots-enabled

- **WHEN** static analysis walks `a2web.log.record`
- **THEN** `LogRecord` is a `@dataclass(slots=True)`, importable as `from a2web.log.record import LogRecord`

### Requirement: NDJSON writer with lazy open

The system SHALL provide `LogWriter` in `src/a2web/log/writer.py`. The writer SHALL hold the resolved log path, an `aiofiles` handle (`None` until first write), and an `asyncio.Lock`. `async write_record(record: LogRecord)` SHALL be the only async-facing entry. The writer SHALL create parent directories on first open. Construction (e.g. inside `register_state`) SHALL NOT touch the filesystem.

#### Scenario: Construction does not create the log file

- **WHEN** `LogWriter(path=tmp_path/"a.ndjson")` is constructed
- **THEN** no file exists at the path; the parent directory may or may not exist

#### Scenario: First write creates parent and file

- **WHEN** `await writer.write_record(record)` runs against a fresh path under a non-existent directory
- **THEN** the directory is created and the file contains exactly one NDJSON line ending with `\n`

#### Scenario: Concurrent writes are serialized

- **WHEN** two concurrent coroutines call `write_record` on the same writer
- **THEN** the resulting file has two lines, each a complete and parseable JSON object (no interleaving)

### Requirement: Size-based rotation with gzip on rollover

The system SHALL define a default rotation threshold of 16 MiB per active file. After each append, the writer SHALL check the file size; if the threshold is crossed, the writer SHALL close the handle, rename the active file to `fetches-YYYY-MM-DD-NN.ndjson` (where `NN` is the next zero-padded sequence), gzip the rolled file via `asyncio.to_thread`, and open a fresh active file at `fetches-YYYY-MM-DD.ndjson`.

#### Scenario: Rollover when threshold crossed

- **WHEN** the active file size after a write exceeds the threshold
- **THEN** the file is renamed to a `-NN.ndjson` form, gzipped to `-NN.ndjson.gz`, and a new active file is opened on the next write

#### Scenario: Sequence numbering survives multiple rollovers in one day

- **WHEN** the active file rolls over twice in the same calendar day
- **THEN** two distinct `fetches-YYYY-MM-DD-01.ndjson.gz` and `fetches-YYYY-MM-DD-02.ndjson.gz` files exist in the log dir

### Requirement: Log path resolution

The system SHALL resolve the log directory in `src/a2web/log/paths.py` as: `$A2WEB_LOG_DIR` if set, else `~/.a2web/logs/`. The resolution SHALL respect `~` expansion and create no side effects.

#### Scenario: $A2WEB_LOG_DIR override

- **WHEN** `$A2WEB_LOG_DIR=/tmp/x` is exported
- **THEN** `log_dir()` returns `Path("/tmp/x")`

#### Scenario: Default fallback

- **WHEN** `$A2WEB_LOG_DIR` is unset
- **THEN** `log_dir()` returns `Path.home() / ".a2web" / "logs"`

### Requirement: Best-effort writes

The system SHALL NOT fail a fetch because of a log write error. If `write_record` raises (disk full, permissions, fd exhaustion), the orchestrator SHALL catch the exception, append an `OperatorHint(code="log_write_failed", message=...)` to the response, route a WARNING through `structlog`, and return the `FetchResponse` as if the log had succeeded.

#### Scenario: Permission error on write does not propagate

- **WHEN** the writer is configured against a read-only directory and a fetch runs
- **THEN** the fetch returns a populated `FetchResponse` with `operator_hints` containing one entry whose `code == "log_write_failed"`, and the response status reflects the fetch outcome (not the log failure)

### Requirement: Opt-out via settings

The system SHALL add `log_enabled: bool = True` to `AppSettings`. When the resolved value is `False`, `register_state` SHALL assign a no-op `LogWriter` to `state.log_writer` whose `write_record` is a successful coroutine that performs no I/O.

#### Scenario: Disabled writer never touches the filesystem

- **WHEN** `A2WEB_LOG_ENABLED=false` is exported, the App is constructed, and a fetch runs
- **THEN** no files are created under the log directory and `state.log_writer.write_record(...)` returns successfully without any disk I/O

### Requirement: Log reader iterates records from active and rolled files

The system SHALL provide `log/reader.py` with three pure functions over the log directory returned by `log_dir()`:

- `iter_records(*, since: timedelta | None = None, host: str | None = None) -> Iterator[LogRecord]` — yields records oldest-to-newest from `fetches-*.ndjson` and `fetches-*.ndjson.gz`. Filters apply in-stream.
- `find_last_for_url(url: str) -> LogRecord | None` — walks newest-to-oldest; returns the first record whose `url` exactly matches.
- `grep_records(pattern: str, *, limit: int = 50) -> list[LogRecord]` — case-insensitive substring match against the serialized record. Stops after `limit` matches.

Malformed lines (invalid JSON or missing required fields) SHALL be skipped silently. Gzipped rolled files SHALL be opened transparently.

#### Scenario: replay returns most recent matching record

- **WHEN** the log contains three records for `https://example.com/x` written at 09:00, 10:00, 11:00
- **THEN** `find_last_for_url("https://example.com/x")` returns the 11:00 record

#### Scenario: gzipped rolled files are read

- **WHEN** the log directory contains `fetches-2026-05-09.ndjson.gz` and `fetches-2026-05-10.ndjson`
- **THEN** `iter_records()` yields records from both files in chronological order

#### Scenario: malformed lines do not raise

- **WHEN** the active NDJSON has a malformed JSON line in the middle
- **THEN** `iter_records()` skips it and continues with subsequent valid lines

### Requirement: LogsRouter exposes replay / tail / grep

The system SHALL provide `LogsRouter` with three `@a2kit.read()` tools:

- `replay(url: str) -> LogReplayResponse` — last record for URL; populates a re-rendered `narrative` string from the diagnostics array; returns 404-style `not_found` envelope when no record matches.
- `tail(n: int = 20, since: str | None = None) -> LogTailResponse` — last `n` records; when `since` is set (e.g., `"1h"`, `"24h"`, `"7d"`), filters to records within that duration.
- `grep(pattern: str, n: int = 50) -> LogGrepResponse` — case-insensitive substring search; returns up to `n` matches, newest-first.

Response models SHALL live at module scope (a2kit antipattern #2). Tools SHALL execute synchronous reader calls inside `asyncio.to_thread`.

#### Scenario: replay surfaces last record

- **WHEN** an operator runs `a2web logs replay --url=https://nyt.com/article` after fetching that URL
- **THEN** the response carries the LogRecord fields plus a one-line `narrative`

#### Scenario: tail with since duration

- **WHEN** `a2web logs tail --since=1h` runs and the log has records spanning 24h
- **THEN** only records with `ts >= now - 1h` are returned

#### Scenario: grep returns matches newest-first

- **WHEN** `a2web logs grep --pattern=paywall` runs against a log with mixed records
- **THEN** the response contains records whose serialized form contains `paywall` (case-insensitive), ordered newest-first

