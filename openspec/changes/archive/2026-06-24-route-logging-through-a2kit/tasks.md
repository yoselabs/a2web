## 1. Sync emit helper

- [x] 1.1 Add `src/a2web/log.py` exposing `log_debug/log_info/log_warning/log_error(event: str, **fields)` that emit on `logging.getLogger("a2kit")` with `extra={"a2kit_fields": dict(fields)}` (mirror a2kit's `emission._emit` sync half)
- [x] 1.2 Add a unit test asserting a `log_warning("e", k=v)` record lands on the `a2kit` logger with `record.a2kit_fields == {"k": v}` and message `"e"` — field-shape-identical to an `await a2kit.log.warning(...)` record

## 2. Migrate async emit sites

- [x] 2.1 `handlers/twitter.py:117` — `_LOG.debug("nitter_instance_skipped", ...)` → `await a2kit.log.debug("nitter_instance_skipped", ...)`; drop the module `structlog` logger
- [x] 2.2 `llm_eval/runner.py:241,371,395` — the three `_LOG.warning(...)` (`eval_system_failed`, `clarity_judge_failed`, `next_links_judge_failed`) → `await a2kit.log.warning(...)`; drop the module `structlog` logger
- [x] 2.3 `fetcher.py` — replace the module `structlog` logger; migrate any emit sites to `await a2kit.log.*` (async pipeline context); confirm none remain via grep

## 3. Migrate sync emit sites + fix altitude

- [x] 3.1 `_plugin.py` — `_try_register` / `load_surface_sorted`: `plugin_manifest_wrong_type` → `log_warning`; provider-surface `plugin_unavailable` → `log_debug`; non-provider surfaces keep `log_info`/`log_warning` per operator-expectation (D3); drop the module `structlog` logger
- [x] 3.2 `llm_resource.py::_build` — resolved fallback emits nothing at `info`+ (per-miss already `debug` via 3.1); chain-exhausted does NOT log a `warning` — its `unavailable_reason` flows to the existing `OperatorHint` path
- [x] 3.2b `ask` response path — turn the no-provider `unavailable_reason` into an `OperatorHint` with an actionable message (set API-key env var / log into Claude Code); confirm `ask` degrades-with-hint (does not raise solely for the missing provider, `fetch_raw` unaffected)
- [x] 3.3 `fetcher_response.py:86` (`_project_routing` `llm_wobble` closed-enum) → `log_warning`/`log_debug` via helper; drop the module `structlog` logger
- [x] 3.4 `wobble/_internal.py:105` (`emit_wobble` `llm_wobble`) → helper emit; drop the module `structlog` logger

## 4. Drop structlog dependency + LDD scrub

- [x] 4.1 Remove `structlog` from `pyproject.toml` dependencies; `uv sync`; confirm nothing else imports it (`grep -rn "import structlog" src tests`)
- [x] 4.2 Scrub "LDD" terminology from live-code comments/docstrings: `server.py`, `models.py`, `cookie_jar.py`, `routers.py`, `_manifests/sinks/__init__.py`, `fetcher.py`, `tiers/browser.py`, `events/{__init__,types,sinks}.py`, `llm_eval/{events,live_sink,runner}.py`, and two test docstrings — keep functionality, drop the word
- [x] 4.3 Rename `llm_eval/runner._ldd_ambient` → `_log_ambient` (and its call site); update `CLAUDE.md`'s 8 LDD references to describe plain `a2kit.log`

## 5. Architecture invariants

- [x] 5.1 Add `tests/architecture/test_no_rogue_structlog.py` walking `src/a2web/**.py`, asserting zero `structlog.get_logger(` call sites (match existing `tests/architecture/` AST/source style)
- [x] 5.2 Add a `test_no_ldd_terminology` check (or extend the above) asserting no `ldd` token remains in `src/a2web/**.py` or `CLAUDE.md` (case-insensitive, word-boundary)
- [x] 5.3 Run the new tests; confirm they pass after migration and fail on reintroduction (spot-check)

## 6. Behavioral tests + docs

- [x] 6.1 Audit and update log-asserting tests to read records off the `a2kit` logger (via `conftest.py` autouse `ambient_for_tests_autouse` / `a2kit.testing` helpers) instead of scraping stdout/structlog output
- [x] 6.2 Add a behavioral test: with `A2KIT_LOG__ENABLED=false`, a code path that previously emitted `plugin_unavailable` writes nothing to stdout/stderr (covers the kill-switch + no-stdout requirements)
- [x] 6.3 Add a test asserting the provider-fallback happy path (resolved `claude-code` after `anthropic` unavailable) emits no `info`+ record; and that the no-provider `ask` path returns an `OperatorHint` with an actionable message instead of raising
- [x] 6.4 Correct the stale `CLAUDE.md` convention line ("Structured logging via structlog + bind_contextvars") to describe the single managed `a2kit` channel + the sync-helper seam

## 7. Verify

- [x] 7.1 `grep -rni "structlog\|\\bldd\\b" src/a2web CLAUDE.md` returns zero live-code hits
- [x] 7.2 `make check` passes (lint + ty + tests, coverage ≥85%)
- [x] 7.3 Manual smoke: run `a2web web ask` on a URL needing extraction with default logging — confirm no `plugin_unavailable`/diagnostic lines on stdout/stderr; re-run with `A2KIT_LOG__STDERR_SINK=pretty` and confirm the records appear on stderr
