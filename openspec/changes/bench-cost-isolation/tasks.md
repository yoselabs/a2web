## 1. Cost guard (the primitive)

- [ ] 1.1 Author `llm-cost-guard`: `assert_within_budget(provider, model, policy)` + a model→tier table + `CostViolation`, and `with_cost_guard(provider, policy)` that wraps a provider so every `complete()` is checked. Substrate-indifferent — no a2web domain imports (packages boundary).
- [ ] 1.2 Default policy: `claude-code:*` allow; `anthropic:haiku-*` allow; `openai_compatible:{cheap ids}` allow; DENY `anthropic:sonnet-*/opus-*`, `openai_compatible:gpt-4*`, and unknown pairs.
- [ ] 1.3 Unit tests: each allow/deny pair; unknown pair denied; wrapped provider raises before issuing the call.

## 2. Wire the guard into the bench (impossible-by-construction)

- [ ] 2.1 In `src/a2web/llm_eval/__main__.py`, acquire the provider only via `with_cost_guard(select_provider(...), policy)` — no un-guarded provider reaches the runner or judges.
- [ ] 2.2 Default `A2WEB_BENCH_PROVIDER=claude-code` on the `bench`/`eval` Makefile targets; keep the fail-loud `LLMNotAvailable` when the session is absent. Metered `anthropic` (cheap only) reachable solely under explicit opt-in.
- [ ] 2.3 Guard against `eval/_prod_env.py` silently supplying a metered key path — document + test that a Sonnet-on-metered attempt raises `CostViolation`, not a bill.

## 3. Provenance stamping

- [ ] 3.1 Capture resolved `provider` + `model` in the run context; write into the `eval/runs/<date>` artifact header (`report.py`).
- [ ] 3.2 Stamp provider+model per cell in `runner.py::_run_one` output.
- [ ] 3.3 Test: artifact records the stamped pair; a metered run is identifiable from its artifact alone.

## 4. Isolation flags

- [ ] 4.1 Add `--slug`/`--id` corpus-item filter in `__main__.py` (alongside `--only <class>`); fail loud on 0 matches.
- [ ] 4.2 Add per-axis select/skip flags; make `runner.py:289-297` honor them (default = all axes, preserving current behavior).
- [ ] 4.3 Tests under `tests/capabilities/output_benchmark/` covering `--slug`, single-axis, and the combination.

## 5. Verification

- [ ] 5.1 `make check` green.
- [ ] 5.2 Live: `A2WEB_BENCH_PROVIDER=claude-code make bench ARGS="--slug <one> --axis quality"` runs a single guarded, stamped cell on the subscription provider — confirm zero metered spend and the artifact stamp.
- [ ] 5.3 Negative live check: forcing a Sonnet-on-metered config raises `CostViolation` before any call.

## 6. Shelf (defer promotion to build time)

- [ ] 6.1 At build time, run the shelf loop (`<shelf>/docs/agent-loop.md`) and promote `llm-cost-guard` as a primitive. Do NOT promote the broader harness (rule-of-three: one consumer). Keep a2web's provider-policy / provenance-record / isolation-filter seams clean for later.
