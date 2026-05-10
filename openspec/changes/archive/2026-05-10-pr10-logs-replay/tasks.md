# Implementation Tasks

## 1. Log reader

- [ ] 1.1 Create `src/a2web/log/reader.py` with `iter_records`, `find_last_for_url`, `grep_records`
- [ ] 1.2 Walk active NDJSON + rolled `.ndjson.gz` files in `log_dir()`
- [ ] 1.3 Parse each line with json.loads → LogRecord fields; skip malformed lines silently
- [ ] 1.4 `find_last_for_url`: walk newest-first; exact URL match preferred; no host fallback in v1
- [ ] 1.5 Tests: synthetic NDJSON fixture; gzipped rotation; exact-match find; grep ignore-case; bad lines skipped

## 2. Duration parsing

- [ ] 2.1 Create `src/a2web/utils/duration.py` with `parse_duration("1h" | "30m" | "7d") -> timedelta`
- [ ] 2.2 Tests: each suffix; bad input raises ValueError

## 3. Routers refactor + LogsRouter

- [ ] 3.1 Convert `src/a2web/routers.py` → `routers/` package
- [ ] 3.2 Move existing `WebRouter` to `routers/web.py`; re-export from `routers/__init__.py`
- [ ] 3.3 Create `routers/logs.py` with `LogsRouter` and three `@a2kit.read()` tools
- [ ] 3.4 Define response pydantic models at module scope: `LogReplayResponse`, `LogTailResponse`, `LogGrepResponse`
- [ ] 3.5 Register `LogsRouter()` in `server.py`
- [ ] 3.6 Tests: routing dispatch, monkey-patched log dir, replay/tail/grep happy paths

## 4. Gate

- [ ] 4.1 `make lint` clean
- [ ] 4.2 `make ty` clean
- [ ] 4.3 `make test` green, coverage ≥85%
- [ ] 4.4 Update `CLAUDE.md` (logs router; CLI surface; PR10b deferred items)
- [ ] 4.5 Commit `PR10: a2web logs replay/tail/grep CLI`
- [ ] 4.6 Archive change via `openspec archive pr10-logs-replay`
