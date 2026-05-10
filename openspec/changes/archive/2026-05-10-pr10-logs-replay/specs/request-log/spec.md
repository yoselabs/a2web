## ADDED Requirements

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
