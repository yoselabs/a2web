## 1. Settings update — `src/a2web/settings.py`

- [x] 1.1 Add `log_enabled: bool = True` to `AppSettings`
- [x] 1.2 Verify `A2WEB_LOG_ENABLED=false` env override is honored (no new test needed; existing precedence test already covers boolean parsing)

## 2. Path resolution — `src/a2web/log/paths.py`

- [x] 2.1 Create `src/a2web/log/__init__.py` (empty re-export)
- [x] 2.2 `src/a2web/log/paths.py` — `def log_dir() -> Path` returning `$A2WEB_LOG_DIR` (expanded) when set, else `~/.a2web/logs`. Pure function, no side effects
- [x] 2.3 `def active_log_path(now: datetime | None = None) -> Path` returning `log_dir() / f"fetches-{YYYY-MM-DD}.ndjson"`

## 3. Record schema — `src/a2web/log/record.py`

- [x] 3.1 Define `LogRecord` as `@dataclass(slots=True)` with fields per the spec
- [x] 3.2 Provide `to_json(self) -> str` returning a single-line JSON encoding (no newlines in the body)
- [x] 3.3 Provide `from_response(response: FetchResponse) -> LogRecord` derivation helper. Compact each Diagnostic to `{"step", "verdict", "dur_ms"}` for log payload (omit verbose `extra`)

## 4. Rotation — `src/a2web/log/rotation.py`

- [x] 4.1 `DEFAULT_ROTATION_BYTES = 16 * 1024 * 1024`
- [x] 4.2 `def next_rolled_path(active: Path, *, now: datetime | None = None) -> Path` — produces `fetches-YYYY-MM-DD-NN.ndjson` with `NN` = next available zero-padded two-digit sequence in the dir
- [x] 4.3 `def gzip_file(src: Path) -> Path` — sync helper compressing `src` to `src.with_suffix(src.suffix + ".gz")`, removing `src` on success. Returns the gz path
- [x] 4.4 Wrap `gzip_file` for async use via `asyncio.to_thread` from the writer

## 5. Writer — `src/a2web/log/writer.py`

- [x] 5.1 Define `LogWriter` as a regular class (NOT dataclass — holds runtime state) with `__slots__` for `_path_factory`, `_handle`, `_lock`, `_threshold_bytes`, `_disabled`
- [x] 5.2 Constructor `__init__(self, *, path_factory=active_log_path, threshold_bytes=DEFAULT_ROTATION_BYTES, disabled=False)` — does NOT touch the filesystem
- [x] 5.3 `async def write_record(self, record: LogRecord) -> None`:
  - if `disabled`: return immediately
  - acquire `self._lock`
  - lazy-open `self._handle` via aiofiles if not yet open
  - write `record.to_json() + "\n"` and flush
  - check size; if > threshold, close handle, rename to next_rolled_path, gzip via to_thread, set handle = None (next write will reopen)
- [x] 5.4 `async def aclose(self) -> None` — close the active handle if open. Used in tests; no production caller in PR4

## 6. State updates — `src/a2web/state.py`

- [x] 6.1 Update `register_state` to construct `LogWriter(disabled=not resolved.log_enabled)` and assign to `state.log_writer`
- [x] 6.2 No filesystem touches at register time (writer is lazy-open)

## 7. Fetcher integration — `src/a2web/fetcher.py`

- [x] 7.1 After building the `FetchResponse`, derive a `LogRecord` via `LogRecord.from_response(response)`
- [x] 7.2 Try `await state.log_writer.write_record(record)` inside a `try/except`. On exception: append `OperatorHint(code="log_write_failed", message=str(exc))` to `response.operator_hints` and route a WARNING via `structlog.get_logger("a2web").warning(...)`. Do NOT re-raise
- [x] 7.3 Return the (possibly hint-augmented) response

## 8. Tests — `tests/test_log_writer.py`

- [x] 8.1 Construction does not create the file
- [x] 8.2 First write creates parent dir + file with one valid JSON line ending in `\n`
- [x] 8.3 Two concurrent `write_record` calls produce two valid lines, no interleaving
- [x] 8.4 Disabled writer is a no-op (no file created even after many writes)
- [x] 8.5 Rotation triggers when size exceeds threshold; previous file is gzipped and a fresh active file opens
- [x] 8.6 Sequence numbering survives multiple rollovers in one day (`-01.gz`, `-02.gz`)

## 9. Tests — `tests/test_log_record.py`

- [x] 9.1 `LogRecord` is module-scope dataclass with slots
- [x] 9.2 `to_json` is single-line, parseable, contains all required fields
- [x] 9.3 `from_response` derivation: maps `FetchResponse` fields to `LogRecord` fields correctly; compresses diagnostics to step/verdict/dur_ms triples

## 10. Tests — `tests/test_log_paths.py`

- [x] 10.1 `$A2WEB_LOG_DIR` override returns the expanded path
- [x] 10.2 Default returns `~/.a2web/logs`
- [x] 10.3 `active_log_path` honors a fixed `now` for date-stamping

## 11. Tests — fetcher integration

- [x] 11.1 Update `tests/test_fetcher.py` (or add new): a successful fetch through the mock tier appends one record to the log file
- [x] 11.2 A block-page fetch also appends one record (status=failed, verdict=block_page_detected)
- [x] 11.3 Disabled log writer: a fetch runs, no log file is created
- [x] 11.4 Permission error on the log dir: fetch succeeds, response has `operator_hints` with `code="log_write_failed"`

## 12. Quality gate

- [x] 12.1 `make lint` clean (especially ASYNC100/210/230)
- [x] 12.2 `make ty` clean, zero `# ty: ignore`
- [x] 12.3 `make test` green, coverage ≥85%
- [x] 12.4 `make check` clean

## 13. Smoke

- [x] 13.1 `uv run a2web web fetch --url=https://example.com` — confirm a record appears at `~/.a2web/logs/fetches-YYYY-MM-DD.ndjson`
- [x] 13.2 `tail -1 ~/.a2web/logs/fetches-*.ndjson | jq` returns a parseable record
- [x] 13.3 `A2WEB_LOG_ENABLED=false uv run a2web web fetch --url=...` — no log file created

## 14. Docs + commit

- [x] 14.1 Update `CLAUDE.md`: log section under architecture; mention the lazy-open + rotation contract; document the `log_write_failed` hint
- [x] 14.2 Update `README.md` with a "Inspecting the log" section: file location, three jq one-liners (recent failures, p50/p95, hit rate by tier)
- [x] 14.3 Single commit "PR4: NDJSON request log writer"
- [x] 14.4 Wire a2web into the user's daily Claude Code subagent flow (dogfood gate); capture observations as Kay signals in `Evolution/signals/`
- [x] 14.5 Hand off to PR5 (site handlers — Reddit + HN)
