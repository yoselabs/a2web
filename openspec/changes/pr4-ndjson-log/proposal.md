## Why

Three PRs in, a2web fetches real URLs but everything that happens during a fetch is invisible the moment the call returns. The NDJSON request log changes that — every fetch writes one structured record on disk, and standard Unix tools (`tail`, `grep`, `jq`) handle inspection. This is also the dogfood gate the prompt called out: by end of PR4, a2web should be wired into the daily Claude Code subagent flow with the log feeding back into improvements.

## What Changes

- Add `src/a2web/log/__init__.py`, `src/a2web/log/writer.py`, `src/a2web/log/record.py`, `src/a2web/log/rotation.py`, `src/a2web/log/paths.py` — the writer-side stack.
- `LogRecord` is a `@dataclass(slots=True)` at module scope shaping the canonical fetch record (timestamp, url, final_url, host, tier, status, verdict, cache, total_ms, content_chars, compact diagnostics, title, optional error).
- `LogWriter` holds the resolved log path, an `aiofiles` handle (lazy-opened on first write), and an `asyncio.Lock`. Single async `write_record(record)` chokepoint. Rotation check is amortized into the same call.
- Rotation is size-based (default 16 MiB per file) with gzip on rollover; daily filename pattern (`fetches-YYYY-MM-DD.ndjson`, rolled files become `fetches-YYYY-MM-DD-NN.ndjson.gz`).
- Update `src/a2web/state.py` so `register_state` constructs a `LogWriter` (lazy first-write open, no eager file creation) and assigns it to `state.log_writer`.
- Update `src/a2web/fetcher.py` to emit one `LogRecord` per fetch via `state.log_writer.write_record(...)` after the orchestrator builds the `FetchResponse`. Best-effort: write failure SHALL NOT fail the fetch — the orchestrator catches the exception, appends an `operator_hint`, and routes a WARNING to stderr via `structlog`.
- Update `AppSettings` with `log_enabled: bool = True`. Setting to `false` (via `A2WEB_LOG_ENABLED=false` or YAML) makes `state.log_writer` a no-op writer for opt-out scenarios (CI, sensitive runs).
- Add `aiofiles>=24,<25` and `structlog>=24,<25` (already declared) — one new top-level dep.
- Tests: unit tests for `LogRecord` shape, rotation behavior (size threshold + gzip on rollover), no-op writer when disabled, integration test that running a real fetch (against a mock tier) appends one record to the log and round-trips through `gzip` after rollover.
- README adds a short "Inspecting the log" section with three jq one-liners (recent failures by host, p50/p95 `total_ms`, hit rate by tier).
- **No `a2web logs` CLI**. Standard Unix tools (`tail`, `grep`, `jq`) cover tail/grep/stats; the replay subcommand that's genuinely a2web-specific lands in PR10.

## Capabilities

### New Capabilities

- `request-log`: NDJSON request log writer + log path / rotation contract + `LogRecord` schema. Reader-side is operator's choice (jq, awk, custom).

### Modified Capabilities

- `app-state`: `AppState.log_writer` is no longer `None` after `register_state` — it carries a (lazy-open) `LogWriter` instance unless `log_enabled=False`.
- `app-composition`: every successful or failed fetch produces exactly one log record on disk (or a no-op when `log_enabled=False`). Side-effect contract.

## Impact

- **Code**: 5 new files in `src/a2web/log/`, plus tests. ~250–350 LOC (smaller than the dropped CLI surface).
- **Public surface**: `state.log_writer` becomes a public field other PRs can write to. `LogRecord` shape is locked — adding fields is fine; renaming or removing is breaking for log consumers.
- **Filesystem**: a2web now writes to `~/.a2web/logs/` by default (override via `$A2WEB_LOG_DIR`). Documented in README.
- **Dependencies**: add `aiofiles>=24,<25`. `structlog` already declared in `pyproject.toml`.
- **Performance**: per-fetch log overhead ≈ 1–3 ms (one async write of a small JSON object). Rotation check is amortized — once per N writes.
- **Defer**: FastMCP lifespan / anyio TaskGroup deferred to PR7 (browser/proxy pools are the first long-lived consumers). PR3's per-fetch sqlite open/close already works in both CLI and MCP; spending PR4 on a hook with no consumer is build-from-imagination.
- **Operator privacy**: log records include URL, host, tier, status, timing — never response body, never headers. Operators with sensitive URLs set `A2WEB_LOG_ENABLED=false`.
- **No CLI maintenance burden**: tail/grep/stats are standard Unix surface. Adding a CLI wrapper means we'd be testing and documenting it forever for marginal value over `cat | jq`.
