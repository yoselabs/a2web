## 1. Validate a2kit mechanics (spike)

- [x] 1.1 Write a throwaway in-process test: `app.provide(Provider, f)` with the Protocol key; a factory param typed `Lazy[Provider]`; confirm it resolves. Confirm a `ResourceUnavailable` raised inside `f` propagates through `await lazy_provider()` unwrapped. Record the result in the change notes.
- [x] 1.2 Decision gate: if propagation works, proceed with DI (D1). If a2kit wraps/swallows the exception, fall back to a `provider: Lazy[Provider]` constructor kwarg supplied by `bootstrap_state`/`server.py` — same downstream design, no DI `provide(Provider, …)`. Note the chosen path.

## 2. Production wiring

- [x] 2.1 Add `build_selected_provider(settings) -> Provider` (calls `select_provider`; raises `ResourceUnavailable(reason)` on `None`) and register `app.provide(Provider, build_selected_provider)` in `server.py`, before `build_llm_extractor`.
- [x] 2.2 Change `build_llm_extractor` to `(settings, sqlite, provider: Lazy[Provider])` and `LlmExtractorResource.__init__` to accept `provider: Lazy[Provider]`. In `_build`, `await` the injected provider instead of calling `select_provider`.
- [x] 2.3 Delete `LlmExtractorResource.unavailable_reason` and the `None`-return-on-unavailable contract; `extract()` now lets `ResourceUnavailable` propagate.

## 3. Orchestrator: one unavailability path

- [x] 3.1 Restructure `fetcher._phase_extract_answer` so a single `try/except ResourceUnavailable` wraps both the `await fc.llm_extractor()` resolution and the `extract()` call; build the `llm_unavailable` OperatorHint once from `ResourceUnavailable.reason`. Remove the `extract() is None` branch and the `unavailable_reason` read.

## 4. Bench rewire

- [x] 4.1 In `llm_eval/__main__`, thread the `_pick_provider` result into `bootstrap_state(settings, provider=provider)` (wrapping it as `Lazy[Provider]`); add the optional `provider` param to `bootstrap_state` + `build_llm_extractor` plumbing.
- [x] 4.2 Delete the `AppSettings(llm_provider=provider_id)` re-injection, the `cast("ProviderMode", …)`, and the `TYPE_CHECKING ProviderMode` import. Keep `provider_id` only for the run banner.

## 5. Test migration

- [x] 5.1 Migrate the 5 "inject a mock provider" sites (`test_router_wire.py:64,227`, `test_ask_response.py:95`, `test_fetcher_ask.py:105`, `test_llm_eval_systems.py:273`) to supply a `Lazy[Provider]` (or DI override) instead of poking `_extractor`; verify each still passes (watch the model-label / cache-wiring deltas).
- [x] 5.2 Migrate the 3 "force unavailable" sites (`test_ask_response.py:93`, `test_fetcher_ask.py:102`, `test_llm_eval_systems.py:302`) to an `unavailable_lazy(Provider, reason=…)` stub; update any `extract() is None` assertions to expect `ResourceUnavailable` / the `llm_unavailable` hint.

## 6. Verify

- [x] 6.1 `make check` green (lint + ty + test ≥85% + arch).
- [x] 6.2 Confirm parity: production resolves the same provider lazily on first `ask`; the no-LLM path still emits `llm_unavailable` and degrades to raw; extraction + output-benchmark capability tests pass unchanged.
