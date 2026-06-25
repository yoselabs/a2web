## Why

`LlmExtractorResource` is the only LLM consumer that **selects its own provider internally** instead of accepting one. Every other resource is supplied by the DI container; the provider is the exception. That single deviation forces three workarounds: the bench mutates `settings.llm_provider` to steer the resource's internal pick (the re-injection + Tier-1 `cast`), ~8 tests poke the private `_extractor`/`_unavailable_reason` to bypass selection, and the "no LLM" path is handled **twice** in `_phase_extract_answer` (once as `ResourceUnavailable` when the resource isn't provisioned, once as a `None` return + `unavailable_reason` when it is provisioned but selection failed). Making the resource accept its provider via DI — with `select_provider` registered as the global `Provider` factory — removes all three and unifies "no LLM" onto the one `ResourceUnavailable` seam the browser and cookie resources already use.

## What Changes

- Register the global provider factory in DI: `app.provide(Provider, build_selected_provider)` in `server.py`, where the factory calls `select_provider(settings)` and raises `ResourceUnavailable(reason)` when nothing resolves.
- `LlmExtractorResource` accepts `provider: Lazy[Provider]` and **stops selecting internally** — `_build` awaits the injected provider instead of calling `select_provider`. The `unavailable_reason` property and the `None`-return-on-unavailable contract are **removed**.
- **BREAKING (internal):** `extract()` no longer returns `None` when the LLM is unavailable — awaiting the unavailable provider raises `ResourceUnavailable`, which propagates to the orchestrator.
- Collapse the two no-LLM branches in `fetcher._phase_extract_answer` into a single `try/except ResourceUnavailable` wrapping both resolution and `extract()`; the `llm_unavailable` OperatorHint is built once, from `ResourceUnavailable.reason`.
- `build_llm_extractor` / `bootstrap_state` thread a `Lazy[Provider]`; the bench supplies the provider it already selected for the judges (dropping the `AppSettings(llm_provider=provider_id)` re-injection **and** the Tier-1 `cast`/`ProviderMode` import).
- Tests supply a fake `Provider` (DI override or a `Lazy[Provider]` thunk) instead of poking `_extractor`; the 3 "force unavailable" tests pass an `unavailable_lazy(Provider, reason=…)` stub. ~8 private-attribute pokes removed.
- **First task is a validation spike** confirming the a2kit mechanics: `provide(Provider, …)` with a Protocol key, `Lazy[Provider]` resolved in a factory param, and a factory-raised `ResourceUnavailable` propagating through the `await`.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `provider-selection`: adds requirements that the selected provider is **injected** into the extraction resource (the resource never selects internally) and that "no provider available" travels the **single** `ResourceUnavailable` seam shared with other Lazy resources.

## Impact

- **Code:** `src/a2web/server.py` (new `provide(Provider, …)`), `src/a2web/llm_resource.py` (resource takes `Lazy[Provider]`, drop internal selection + `unavailable_reason` + the `select_provider` call), `src/a2web/state.py` (`build_llm_extractor` + `bootstrap_state` thread `Lazy[Provider]`; the DI factory `build_selected_provider`), `src/a2web/fetcher.py` (`_phase_extract_answer` collapse + `FetchContext` already non-optional), `src/a2web/llm_eval/__main__.py` (drop re-injection + `cast` + `ProviderMode` import; supply provider to `bootstrap_state`).
- **Tests:** ~8 sites in `tests/capabilities/ask_response/*`, `tests/capabilities/extraction/test_llm_eval_systems.py` migrate off `_extractor`/`_unavailable_reason` pokes; any test asserting `extract() is None` updates to expect `ResourceUnavailable`.
- **Behavior:** no external change — production resolves the same provider lazily on first `ask`; "no LLM" still degrades to `fetch_raw` + the `llm_unavailable` OperatorHint (same code, same wording). Cold start unchanged (provider built only on first `ask`).
- **Dependency / wire:** no new top-level dependency; no MCP tool-signature, response-envelope, or settings change. `select_provider` (the function) stays — it is now *also* the DI factory's body and the bench-judge selector.
- **Risk:** hinges on a2kit DI resolving a Protocol-keyed `Lazy[Provider]` and propagating a factory-raised exception through `await` — validated by the spike before any consumer is rewired.
