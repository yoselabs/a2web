# Retire the `request-log` capability

## Why

The `request-log` capability specifies the NDJSON fetch-log subsystem —
`LogRecord` (`src/a2web/log/record.py`), `LogWriter` with lazy open + gzip
rotation (`src/a2web/log/writer.py`), log-path resolution
(`src/a2web/log/paths.py`), best-effort write-and-continue, and an
`AppState.log_writer` opt-out wired through the a2kit-era `register_state`.

**None of that software exists.** Commit `9140fc5` ("refactor: nuke NDJSON fetch
log — cache covers replay", 2026-05-12) deleted the entire layer: the NDJSON
package, `LogWriter`/`LogRecord`, `AppState.log_writer`,
`FetchResponse.to_log_record()`, the write-and-handle block in `fetcher.fetch()`,
and the three log-* test modules. Rationale on record: the cache already covers
hit-keyed replay and the structured `diagnostics` array already ships in the
response envelope, so NDJSON was pure duplication.

The one term that outlived the nuke — `log_enabled` — was re-added later for a
different subsystem (it governs the single `a2web` logger via
`a2web_log.configure(enabled=...)`), and its behaviour is already owned by the
`app-logging` capability ("CLI is quiet by default", the single-mute-point
scenario). Nothing unique to `request-log` survives.

The `reconcile-specs-post-sunset` sweep only reached this capability's
`register_state` residue through its new spec guard
(`tests/architecture/test_no_a2kit_in_specs.py`) — which correctly refused to go
green while a spec still named a retired framework symbol. Term-swapping the two
`register_state` lines would leave a capability that still describes five other
removed modules, i.e. a half-reconciled lie. The honest end-state is retirement.

## What Changes

- REMOVE all six `request-log` requirements (the capability describes deleted
  software). The capability spec file is deleted once empty.
- No source change: the code was already deleted by `9140fc5`; this only makes
  the spec baseline stop describing a subsystem that no longer exists.

## Impact

- Affected specs: `request-log` (retired in full).
- No behavioural change — `request-log` had no live implementation to change.
- `app-logging` remains the sole owner of the surviving `log_enabled` /
  logging-mute behaviour.
