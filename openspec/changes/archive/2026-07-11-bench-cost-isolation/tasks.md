## 0. ADR-0016 (author the dev-loop tenet)

- [x] 0.1 Promote the D0 draft to `docs/adr/0016-never-metered-api-in-dev-loop.md`; set Status: Accepted on apply.
- [x] 0.2 Add the row to `docs/adr/INDEX.md` and a `**Never** …` line to `CLAUDE.md` (disambiguate "provenance" from ADR-0014).

## 1. Cost guard (the primitive)

- [x] 1.1 Author `llm-cost-guard`: `assert_within_budget(provider, model, policy)` + a model→tier table + `CostViolation`, and `with_cost_guard(provider, policy)` that wraps a provider so every `complete()` is checked. Substrate-indifferent — no a2web domain imports (packages boundary). → `src/a2web/packages/llm_cost_guard.py`.
- [x] 1.2 Default policy: `claude-code:*` allow; `anthropic:haiku-*` allow; `openai_compatible:{cheap ids}` allow; DENY `anthropic:sonnet-*/opus-*`, `openai_compatible:gpt-4*`, and unknown pairs.
- [x] 1.3 Unit tests: each allow/deny pair; unknown pair denied; wrapped provider raises before issuing the call. → `tests/packages/test_llm_cost_guard.py`.

## 2. Wire the guard into the bench (impossible-by-construction)

- [x] 2.1 In `src/a2web/llm_eval/__main__.py`, acquire the provider only via `with_cost_guard(select_provider(...), policy)` — no un-guarded provider reaches the runner or judges.
- [x] 2.2 Default `A2WEB_BENCH_PROVIDER=claude-code` on the `bench`/`eval` Makefile targets; keep the fail-loud `LLMNotAvailable` when the session is absent. Metered `anthropic` (cheap only) reachable solely under explicit opt-in.
- [x] 2.3 Guard against `eval/_prod_env.py` silently supplying a metered key path — document + test that a Sonnet-on-metered attempt raises `CostViolation`, not a bill. → `test_default_judge_model_denied_on_metered_anthropic` + `test_guard_raises_before_calling_inner`.

## 3. Provenance stamping

- [x] 3.1 Capture resolved `provider` + `model` in the run context; write into the `eval/runs/<date>` artifact header (`report.py`). → `manifest.json` now carries `provider`.
- [x] 3.2 Stamp provider+model per cell in `runner.py::_run_one` output. → `EvalRow.provider`, in `results.json` rows.
- [x] 3.3 Test: artifact records the stamped pair; a metered run is identifiable from its artifact alone. → `test_provider_stamped_in_report_and_artifacts`.

## 4. Isolation flags

- [x] 4.1 Add `--slug`/`--id` corpus-item filter in `__main__.py` (alongside `--only <class>`); fail loud on 0 matches.
- [x] 4.2 Add per-axis select/skip flags; make the LLM axes honor them (default = all axes, preserving current behavior; deterministic token+contract always run).
- [x] 4.3 Tests under `tests/capabilities/output_benchmark/` covering `--slug`, single-axis, and the combination.

## 5. Verification

- [x] 5.1 `make check` green. → 1100 passed, coverage 90.26% (≥85%), lint + ty + arch clean.
- [ ] 5.2 **LIVE (user-run):** `A2WEB_BENCH_PROVIDER=claude-code make bench ARGS="--slug <one> --axis quality"` — confirm zero metered spend and the artifact `provider` stamp. Needs the Claude Code OS session in the shell; left for the user.
- [x] 5.3 Negative check: forcing Sonnet-on-metered raises `CostViolation` before any call — verified by unit test (`test_guard_raises_before_calling_inner`, asserts the inner provider is never called). Stronger than a live check and deterministic.

## 6. Shelf (defer promotion to build time)

- [ ] 6.1 **DEFERRED (by design):** at build time, run the shelf loop and promote `llm-cost-guard` as a primitive. NOT promoting the harness (rule-of-three: one consumer). a2web's provider-policy / provenance-record / isolation-filter seams are kept clean for later. The guard lives at `packages/llm_cost_guard.py` (domain-independent) until then.
