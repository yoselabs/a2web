## Why

PR10 shipped `LogsRouter` (replay/tail/grep over the NDJSON request log) on the theory that the dogfood loop needed CLI surface. In review the value is thinner than projected: the log is already searchable with `tail`/`grep`/`jq` (engineering.md §4 acknowledged "no bundled CLI" was the original stance), the *useful* half — actually replaying a fetch against a stored body without re-fetching — was deferred to PR10b because the log doesn't store bodies, and shipping read-only convenience tools without the replay payload mainly adds API surface area, ties response models to the log shape, and makes the v0.1 contract bigger than it should be at release time. Cleanest move is to revert PR10 in full before tagging v0.1; the reader can come back later when there's a clear use-case (likely bundled with a real replay-from-cache implementation).

## What Changes

- **BREAKING**: Remove the `LogsRouter` and its three tools (`replay`, `tail`, `grep`). MCP/CLI consumers that called `a2web logs ...` lose this surface. None exist outside the test suite as of today.
- Remove `src/a2web/log/reader.py` (pure read functions over the NDJSON log) — no other module imports it.
- Remove `src/a2web/utils/duration.py` (`parse_duration` was only used by `LogsRouter.tail`).
- Remove the new pydantic response models from `src/a2web/routers.py`: `LogRecordModel`, `LogReplayResponse`, `LogTailResponse`, `LogGrepResponse`, plus the `_to_model` / `_narrative` helpers. Restore `routers.py` to a `WebRouter`-only module.
- Remove `LogsRouter` registration from `src/a2web/server.py`.
- Delete the three test files added by PR10: `tests/test_log_reader.py`, `tests/test_duration.py`, `tests/test_logs_router.py`.
- Revert `tests/test_app_composition.py::test_routers_register_expected_tools` to the pre-PR10 single-tool assertion (`fetch` only).
- Update CLAUDE.md `log/` description: drop the PR10 paragraph; restore the original "no bundled CLI: use `tail`, `grep`, `jq`" stance and note future replay work in `BACKLOG.md` (added by the companion `release-v0-1` change).

NDJSON log format and writer are **untouched** — fetch behavior, persistence, and the existing `tests/test_log_writer.py` / `tests/test_log_record.py` / `tests/test_log_paths.py` keep working unchanged.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `request-log`: removes the three reader requirements added by PR10 (`Log reader iterates records...`, `LogsRouter exposes replay / tail / grep`, plus their scenarios). Writer requirements remain unchanged.

## Impact

- Code: `src/a2web/log/reader.py` (delete), `src/a2web/utils/duration.py` (delete), `src/a2web/routers.py` (revert to WebRouter-only), `src/a2web/server.py` (drop `LogsRouter` import + registration), `src/a2web/utils/__init__.py` (untouched — already empty)
- Tests: delete `tests/test_log_reader.py`, `tests/test_duration.py`, `tests/test_logs_router.py`; revert `tests/test_app_composition.py` to single-tool assertion
- Public surface: removes one MCP/CLI router. Internal surface only — no external consumers known.
- Coverage: total test count drops from 229 → ~201. Coverage % should hold (the deleted tests covered code that's also being deleted).
- Docs: CLAUDE.md `log/` paragraph reverted; BACKLOG.md (created in `release-v0-1`) carries the future-replay note.
- No dependency changes. No migration required.
