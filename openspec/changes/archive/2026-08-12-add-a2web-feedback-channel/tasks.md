## 1. Config surface

- [x] 1.1 Add `A2WEB_FEEDBACK_ENABLED` (bool, default `false`) to `settings.py`, following existing `A2WEB_*` naming conventions
- [x] 1.2 Add `A2WEB_FEEDBACK_ENDPOINT` (str, default `""` — no shipped default; a personal gateway URL fails `tests/architecture/test_no_personal_strings.py`, caught by the full-suite run at 5.3) to `settings.py`
- [x] 1.3 Add `A2WEB_FEEDBACK_API_KEY` (str, secret — add to `_SECRET_FIELDS`, no default — must be explicitly set or reporting silently no-ops) to `settings.py`
- [x] 1.4 Add `A2WEB_FEEDBACK_INCLUDE_CONTENT` (bool, default `false`, independent of `A2WEB_FEEDBACK_ENABLED`) to `settings.py`

## 2. Feedback reporting function

- [x] 2.1 Implement `_record_feedback(fc, state)` in `fetcher/pipeline.py`, alongside `_record_uptake` — same shape: best-effort, `try`/`except` swallowing to `log_warning`, never raises
- [x] 2.2 No-op immediately (before any network call) when `state.settings.feedback_enabled`/`feedback_api_key` is false/empty, or when no `fc.operator_hints` entry has `severity` `warning`/`critical`
- [x] 2.3 Build the OTLP/HTTP logs JSON payload: map hint `code`/`severity`, tier/handler context (last `fc.observations` entry's `source`/`verdict`), and a2web version into log record attributes; exclude raw URL, query, and page content unless `A2WEB_FEEDBACK_INCLUDE_CONTENT` is set
- [x] 2.4 a2web version comes from `a2web.__version__` (`importlib.metadata`-backed, existing convention — `cli.py`/`server.py` both use it)
- [x] 2.5 POST via `httpx` (already a baseline dependency) with header `X-Api-Key: <A2WEB_FEEDBACK_API_KEY>` to `A2WEB_FEEDBACK_ENDPOINT` — NOT `Authorization: Bearer` (confirmed via live probe against the deployed gateway; the auth boundary is Traefik-level, not inside the Collector)
- [x] 2.6 Bound the HTTP call with a 5s client timeout; catch `httpx.HTTPError`/`OSError` and route to `log_warning`, mirroring `_record_uptake`'s `except (aiosqlite.Error, OSError)` pattern

## 3. Wiring

- [x] 3.1 Call `await _record_feedback(fc, state)` from `fetcher/__init__.py`'s `fetch()`, once per fetch (both `query` and `fetch_raw` paths — not gated to the ask path like `_record_uptake`, since a wall/timeout on a raw fetch is equally reportable), right after `_record_uptake`'s call site
- [x] 3.2 Confirmed: the early return in 2.2 (unset flag / empty key) precedes any `httpx.AsyncClient` construction or payload building — zero network capability when off

## 4. Tests

- [x] 4.1 Unit test: flag unset → no HTTP call made, even when a critical hint fires — `tests/capabilities/feedback_telemetry/test_feedback_reporting.py::test_flag_unset_makes_no_http_call` (offline, direct against `_record_feedback`, per `_record_uptake`'s existing test-style precedent — not the `mcp_client` seam, which is heavier than this needs)
- [x] 4.2 Unit test: flag set + critical hint → one HTTP call made, with `X-Api-Key` header and no raw URL/query/content in the payload — `test_critical_hint_sends_one_report_with_api_key_header_and_no_url`
- [x] 4.3 Unit test: flag set + only `info`-severity hints present → no HTTP call made — `test_only_info_hints_makes_no_http_call` (plus `test_flag_set_but_no_api_key_makes_no_http_call` for the key-missing case)
- [x] 4.4 Unit test: flag set + `A2WEB_FEEDBACK_INCLUDE_CONTENT` set + critical hint → payload includes URL/query/content — `test_include_content_flag_adds_url_and_query`
- [x] 4.5 Unit test: feedback POST raises → does not propagate — `test_delivery_failure_does_not_raise`

## 5. Documentation and closeout

- [x] 5.1 Document the new `A2WEB_FEEDBACK_*` env vars — added a "Failure-feedback reporting" row group to `README.md`'s config table
- [x] 5.2 Confirmed with the "OpenObserve and OTEL Collector stack" session against the real payload shape — found and fixed a real gap: the gateway's `redactionprocessor` only covered OTLP `attributes`, not `LogRecord.body` (where the hint's narrative `message` lives), so a URL could leak via body text even with `A2WEB_FEEDBACK_INCLUDE_CONTENT` off. Fixed gateway-side with an OTTL `transform` processor scrubbing `body` unconditionally. Nothing changed on a2web's side. See design.md D3.
- [x] 5.3a `make lint` / `make ty` / full `uv run pytest tests/` all pass (1822 passed, 2 deselected) — caught and fixed two real issues along the way: the missing `feedback_endpoint` default violated `test_no_personal_identifiers_in_the_shipping_tree`, and `_record_feedback`'s original design assumed a log-sink mechanism that doesn't exist (see design.md D1)
- [x] 5.3b Live smoke test: ran `_record_feedback` (the real code path, not mocked) against the real deployed gateway with `feedback_enabled=True`, real endpoint/key → `200 {"partialSuccess":{}}`. One `try_user_browser`-hint report delivered to `a2web_feedback` end to end.
