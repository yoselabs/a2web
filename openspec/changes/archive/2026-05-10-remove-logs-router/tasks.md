# Implementation Tasks

## 1. Delete reader + helper modules

- [ ] 1.1 Delete `src/a2web/log/reader.py`
- [ ] 1.2 Delete `src/a2web/utils/duration.py`
- [ ] 1.3 Confirm `src/a2web/utils/__init__.py` stays (still hosts `time.py`)
- [ ] 1.4 Grep the codebase to confirm no remaining imports of `log.reader` or `utils.duration` outside the routers module

## 2. Restore routers.py to WebRouter-only

- [ ] 2.1 Remove `LogRecordModel`, `LogReplayResponse`, `LogTailResponse`, `LogGrepResponse` from `src/a2web/routers.py`
- [ ] 2.2 Remove `_to_model` / `_narrative` helpers
- [ ] 2.3 Remove the entire `LogsRouter` class
- [ ] 2.4 Drop the now-unused imports: `asyncio`, `pydantic.BaseModel`, `pydantic.Field`, `find_last_for_url`, `grep_records`, `tail_records`, `LogRecord`, `parse_duration`, plus `typing.Any`
- [ ] 2.5 Restore the module docstring to its pre-PR10 wording (single `WebRouter` exposing `fetch`)

## 3. Server registration

- [ ] 3.1 In `src/a2web/server.py`, change the import back to `from .routers import WebRouter`
- [ ] 3.2 Restore `app = register_state(a2kit.App("a2web").add_router(WebRouter()))`

## 4. Tests

- [ ] 4.1 Delete `tests/test_log_reader.py`
- [ ] 4.2 Delete `tests/test_duration.py`
- [ ] 4.3 Delete `tests/test_logs_router.py`
- [ ] 4.4 Revert `tests/test_app_composition.py::test_routers_register_expected_tools` to pre-PR10 single-tool assertion (`fetch` only); rename back to `test_web_router_registers_one_tool`

## 5. Docs

- [ ] 5.1 Update `CLAUDE.md` `log/` paragraph: drop the PR10 reader/router section; restore the original "no bundled CLI: use `tail`, `grep`, `jq`" sentence; reference `BACKLOG.md` for the deferred replay-from-cache work

## 6. Gate

- [ ] 6.1 `make lint` clean
- [ ] 6.2 `make ty` clean
- [ ] 6.3 `make test` green, coverage ≥85%
- [ ] 6.4 Commit `Remove LogsRouter + log reader (revert PR10)`
- [ ] 6.5 Archive change via `openspec archive remove-logs-router`
