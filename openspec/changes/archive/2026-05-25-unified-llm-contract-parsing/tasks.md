# Tasks — unified-llm-contract-parsing

## 1. Define the shared discipline

- [x] 1.1 Create `src/a2web/packages/llm_extract/wobble.py` with `WobbleTolerance` (StrEnum: STRICT / DERIVE / DEFAULT / SKIP), `WobblePolicy` (frozen dataclass with `tolerance`, `default`, `derive_from`), and a `WobbleSkip` sentinel exception used internally to short-circuit a SKIP-fallthrough.
- [x] 1.2 Add `apply_policy(parsed: dict, field: str, policy: WobblePolicy, *, derive: Callable, boundary: str, model: str, raw_excerpt_source: str) -> object` returning the resolved value or raising `WobbleSkip` (SKIP) / re-raising the underlying `KeyError`/`TypeError` as `JudgeParseError`-style (STRICT).
- [x] 1.3 Add `emit_wobble(boundary: str, field: str, policy: WobbleTolerance, *, model: str, raw_excerpt: str) -> None` — the single `_LOG.warning("llm_wobble", ...)` shim. Bound `raw_excerpt` to 200 chars.
- [x] 1.4 Export from `src/a2web/packages/llm_extract/__init__.py`: `WobbleTolerance`, `WobblePolicy`, `apply_policy`, `emit_wobble`, `WobbleSkip`.
- [x] 1.5 Confirm `wobble.py` has zero imports from `a2web.<domain>` (read the import block).

## 2. Migrate `judge.py`

- [x] 2.1 Add module-level `_JUDGE_POLICY: dict[str, WobblePolicy]` mapping `scores`→STRICT, `overall`→STRICT, `reached`→DERIVE, `reasoning`→DEFAULT("").
- [x] 2.2 Add `_derive_reached(parsed: dict, _field: str) -> bool` returning `int(parsed["overall"]) >= 3`. Pure; no logging here.
- [x] 2.3 Replace the manual `try/except` block in `Judge.score` with `apply_policy` calls per field. On DERIVE for `reached`, set `raw["reached_derived"] = True` on the returned verdict.
- [x] 2.4 Verify the legacy `JudgeParseError` raise path still fires for missing `scores` / `overall` (STRICT) and for un-parseable JSON (the `_parse_verdict_json` path is unchanged — pre-policy stage).
- [x] 2.5 Update `tests/packages/llm_extract/test_llm_judge.py`: drop the "missing `reached` raises" negative test; add (a) "missing `reached` derives from `overall>=3`" test, (b) "missing `reached` derives False when `overall<3`" test, (c) keep the "missing `scores` raises" regression test.

## 3. Migrate `extractor.py`

- [x] 3.1 In `_split_answer_and_routing`, add `_ROUTING_POLICY` mapping `answer`/`structural_form`/`shape`→ "SKIP-with-fallthrough-to-(text, None)", `genre`/`obstacle`→DEFAULT(None), `ask_here`/`try_url`→DEFAULT(()).
- [x] 3.2 Refactor the function body to consult the policy. Behavior identical to today; the goal is named-policy not behavior change. Use `WobbleSkip` to short-circuit to `(text, None)`.
- [x] 3.3 In `_split_answer_and_next_links`, document the per-entry SKIP policy (today entries with missing fields are silently dropped). Add an `emit_wobble` call per dropped entry with `boundary="extractor_next_links"`, `field=<first-missing-field>`.
- [x] 3.4 Update `tests/packages/llm_extract/test_extractor.py` (or equivalent) to assert one `llm_wobble` log per dropped entry. Use `structlog.testing.capture_logs` or the project's existing log-capture fixture.

## 4. Migrate `fetcher_response.py::_project_routing`

- [x] 4.1 Replace the `_LOG.warning("routing_validation_failed", ...)` call with `emit_wobble(boundary="fetcher_routing_mirror", field=<violating-field-name>, policy=SKIP, ...)`. Extract the violating field name from the pydantic `ValidationError` if possible (loc[0]); fall back to `"unknown"`.
- [x] 4.2 Existing `routing_validation_failed` test (search tests/ for any consumer) — rename expectation to `llm_wobble`.
- [x] 4.3 No behavior change otherwise; return-`None` semantics preserved.

## 5. Migrate `bench_judge.py`

- [x] 5.1 Add `_CLARITY_POLICY` (`clarity`→STRICT, `reasoning`→DEFAULT("")) and `_NEXT_LINKS_POLICY` (`next_links_score`→STRICT, `reasoning`→DEFAULT("")).
- [x] 5.2 Replace the inline `try/except KeyError/TypeError/ValueError → JudgeParseError` blocks in `score_clarity` and `score_next_links` with `apply_policy` calls.
- [x] 5.3 Confirm `runner.py` paths for `clarity_judge_failed` / `next_links_judge_failed` still fire for STRICT failures (no change to runner.py).
- [x] 5.4 Add tests covering: clarity verdict with missing `reasoning` returns `reasoning=""` and emits one `llm_wobble`; clarity verdict with missing `clarity` still raises `JudgeParseError`.

## 6. Cross-cutting audit + docs

- [x] 6.1 Add `tests/test_llm_boundary_audit.py` — walks `src/a2web/` for files importing `json.loads` AND a `Provider`/LLM call; asserts each declares a `*_POLICY` dict or imports `apply_policy`. Whitelist obvious non-LLM JSON consumers (config loader, etc.).
- [x] 6.2 Add a short "LLM contract parsing" section to `CLAUDE.md` under the existing conventions, pointing at `wobble.py` and the four canonical sites. One paragraph + the policy table reference.
- [x] 6.3 Drop the `harden-judge-parser` change folder if it has not yet been applied (its scope is fully absorbed by tasks 2.1–2.5). If it has been applied, leave the archive entry alone and only swap the open-coded `reached` derivation for the `apply_policy` call.
- [x] 6.4 Run `make check` — coverage ≥ 85%, lint + ty clean. Run `make bench` is **not** required (the migration is behavior-preserving except for the judge `reached` case, which is the targeted regression fix).
