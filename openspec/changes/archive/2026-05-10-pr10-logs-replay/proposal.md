## Why

PR4 shipped the NDJSON request log; every fetch produces one record per line. Today the only way to read it is `tail`/`grep`/`jq` against `~/.a2web/logs/fetches-*.ndjson`. Engineering.md §4 calls this out: *"This is the 'I made a research subagent run and want to know which 3 URLs failed and why' tool. Critical for trust."* Without a CLI surface the operator has to reach for jq every time.

PR10 ships the **read-only** half of `a2web logs`: `replay <url>` (last record for URL), `tail` (recent records), `grep` (pattern search). All three operate over the existing log format — no schema change. The full pipeline-replay flag (`a2web fetch --replay <ts>`, run the orchestrator against a stored body without re-fetching) is intentionally deferred to PR10b: it requires storing response bodies in the log, which is a separate scope-and-storage discussion.

The `LogsRouter` is the third tool router; like `WebRouter` it dispatches both as MCP tools and CLI commands (`a2web logs <verb>`).

## What Changes

- **`log/reader.py`** — new module. Pure functions over the log directory:
  - `iter_records(*, since: timedelta | None = None, host: str | None = None) -> Iterator[LogRecord]` — yields records oldest-to-newest from the active NDJSON plus rolled `.ndjson.gz` files. Filters in-stream so memory is bounded.
  - `find_last_for_url(url: str) -> LogRecord | None` — walks newest-to-oldest, returns first match. Tries exact URL first, then host-only fallback if no exact match.
  - `grep_records(pattern: str, *, limit: int = 50) -> list[LogRecord]` — substring match on serialized record (URL, title, verdict). `re.IGNORECASE`.
  - All readers are sync; routers wrap calls in `asyncio.to_thread` once.
- **`routers/__init__.py`** — split the existing `routers.py` module into a package. Move `WebRouter` into `routers/web.py`, add `routers/logs.py`. Re-export both from `routers/__init__.py` so `server.py`'s import (`from .routers import WebRouter`) keeps working.
- **`routers/logs.py`** — new `LogsRouter` with three read-only tools:
  - `replay(url: str) -> LogReplayResponse` — returns the last record for URL. `LogReplayResponse` is a pydantic model with the LogRecord fields plus a `narrative` field re-rendered from `diagnostics`.
  - `tail(n: int = 20, since: str | None = None) -> LogTailResponse` — last N records, optionally since a duration string (`"1h"`, `"24h"`, `"7d"`).
  - `grep(pattern: str, n: int = 50) -> LogGrepResponse` — substring match.
- **`server.py`** — register `LogsRouter()` alongside `WebRouter()`.
- **`utils/duration.py`** — small helper `parse_duration(s)` for `"1h"` / `"30m"` / `"7d"` style strings used by `tail --since`.

## Capabilities

### Modified Capabilities

- `request-log` — adds three read tools (`replay`, `tail`, `grep`) over the existing NDJSON. Format unchanged; just makes it queryable from the CLI/MCP surface.

## Impact

- `pyproject.toml`: no new deps (gzip is stdlib)
- `src/a2web/log/reader.py`: new, ~120 LOC
- `src/a2web/routers/__init__.py` + `web.py` + `logs.py`: refactor existing single file → package, new logs module ~100 LOC
- `src/a2web/server.py`: 1-line addition (register `LogsRouter`)
- `src/a2web/utils/duration.py`: new, ~15 LOC
- Tests: log reader unit tests (synthetic NDJSON fixtures), LogsRouter integration tests with monkey-patched log dir
- Docs: CLAUDE.md note that the log is now CLI-queryable; tail/grep replace `tail -f | jq` for routine ops

## Out of Scope (deferred to PR10b)

- **`a2web fetch --replay <ts>`** — rerun the orchestrator pipeline against a stored body without re-fetching. Requires either (a) extending LogRecord to carry response body + headers (bloats log significantly), or (b) a separate replay-store that writes alongside the cache. Both are real design choices that deserve their own PR; meanwhile `logs replay <url>` covers the most common operator question ("what happened to URL X").
- **`a2web logs stats --since 7d`** — tier distribution / cost / fail-rate aggregations. Easy to add once the reader infrastructure is in place; defer until usage shows which aggregations matter.
- **`a2web logs export --format csv`** — for offline analysis. Same deferral logic as `stats`.
