# Tasks

## 1. Parser change in `judge.py`

- [x] 1.1 In `src/a2web/packages/llm_extract/judge.py`, add a module-level `_REACHED_DERIVED_THRESHOLD: int = 3` constant near the top of the file, with a one-line docstring tying it to the report-side aggregation in `src/a2web/llm_eval/report.py`.
- [x] 1.2 Add a module-level `structlog` logger (`_LOG = structlog.get_logger("a2web.packages.llm_extract.judge")`), mirroring the pattern in `src/a2web/fetcher_response.py`.
- [x] 1.3 In `Judge.score`, split `reached` out of the strict `try/except` block. After parsing `scores` / `overall` / `reasoning`, branch on `"reached" in parsed and parsed["reached"] is not None`: when present, coerce via `bool(parsed["reached"])` (existing semantics — raise `JudgeParseError` on `TypeError`); when absent or null, derive `reached = overall >= _REACHED_DERIVED_THRESHOLD`, set a local `reached_derived = True`, and emit `_LOG.warning("judge_reached_missing", model=self._model.model, overall=overall, derived_reached=reached)`.
- [x] 1.4 When `reached_derived` is `True`, add `"reached_derived": True` to the `raw` dict on the returned `JudgeVerdict`. When the model returned `reached` explicitly, do not set the key.

## 2. Tests in `tests/packages/llm_extract/test_llm_judge.py`

- [x] 2.1 Delete `test_judge_raises_parse_error_on_missing_field` (the existing negative for missing-`reached`) — its premise is replaced by the derivation scenario.
- [x] 2.2 Add `test_judge_derives_reached_when_missing`: provider returns the canonical bench-failure payload `{"scores":[5,3,5], "overall":4, "reasoning":"..."}`; assert `verdict.reached is True`, `verdict.raw["reached_derived"] is True`, no `JudgeParseError`.
- [x] 2.3 Add `test_judge_derives_reached_when_null`: provider returns `{"scores":[1,0], "overall":1, "reached": null, "reasoning":"miss"}`; assert `verdict.reached is False`, `verdict.raw["reached_derived"] is True`.
- [x] 2.4 Add `test_judge_explicit_reached_does_not_set_derived_flag`: provider returns a fully-formed payload with `reached: true`; assert `"reached_derived" not in verdict.raw` (or value is falsy).
- [x] 2.5 Add `test_judge_missing_overall_still_raises`: provider returns `{"scores":[5], "reasoning":"x"}`; assert `JudgeParseError`.
- [x] 2.6 Add `test_judge_missing_reasoning_still_raises`: provider returns `{"scores":[5], "overall":5}` (no `reached`, no `reasoning`); assert `JudgeParseError` — derivation does not rescue `reasoning`.
- [x] 2.7 Add `test_judge_reached_warning_log_emitted` using `structlog.testing.capture_logs()` (or the project's existing log-capture fixture) to assert `judge_reached_missing` appears with the expected keys.

## 3. Eval regression

- [x] 3.1 In `tests/capabilities/extraction/test_llm_eval_suite.py`, add `test_eval_row_records_derived_verdict_as_success`: stub a Judge whose response omits `reached`; assert the resulting row has `judge_error is None`, `judge_reached` set to the derived bool, and is counted in the system's reach rate by `build_report`.
- [x] 3.2 Confirm the bench wikipedia-rust fixture (the canonical failure case from `eval/runs/2026-05-25_183411/`) is reproduced as a unit-level fixture in step 2.2 above so the regression cannot rot when the live bench is not run.

## 4. Verification

- [x] 4.1 Run `make check` — lint + ty + tests pass; coverage ≥ 85%.
- [x] 4.2 Run `openspec validate harden-judge-parser` — passes.
- [x] 4.3 (Optional, post-merge) re-run `make bench` and confirm the `wikipedia-rust / a2web_extract` cell scores cleanly instead of `judge_failed`. Capture the run path in `eval/findings_<date>.md`. Do not block the change on this — the unit fixture in 2.2 already pins the regression.
