## Context

After `centralize-provider-selection`, selection is one function (`llm_resource.select_provider`). But `LlmExtractorResource` still *calls* it internally during `_build` — it is the only LLM consumer that picks its own provider rather than being handed one. Every other resource (`SqliteResource`, `BrowserPool`, `CookieJarResource`) is supplied by the DI container and surfaced at the tool seam as `Lazy[T]`; "unavailable" rides a shared `unavailable_lazy(cls, reason=…)` stub that raises `ResourceUnavailable` on `await`, caught uniformly in the orchestrator (`fetcher.py:602/641/1424`).

The provider's exceptionalism creates three workarounds, all symptoms of the same root cause:
1. **Bench re-injection** — `AppSettings(llm_provider=provider_id)` mutates settings so the resource's internal pick agrees with the provider the bench already chose for its judges (plus the Tier-1 `cast`/`ProviderMode` import that boundary required).
2. **Test pokes** — ~8 sites set `res._extractor = Extractor(provider=fake, …)` or `res._unavailable_reason = …` to bypass selection.
3. **Double no-LLM handling** — `_phase_extract_answer` catches `ResourceUnavailable` (resource not provisioned, line 1554) *and* checks `extract() is None` + reads `unavailable_reason` (provisioned but selection failed, line 1589).

a2kit DI supports the fix: `provide(type_, factory)` keys on any type including a Protocol (`container.py:154`, keyed by `type_`), and factory params honor `Lazy[T]` (`container.py:364,496` — "receive a deferred closure, same as tool kwargs"). So `app.provide(Provider, build_selected_provider)` + `build_llm_extractor(settings, sqlite, provider: Lazy[Provider])` is mechanically supported.

## Goals / Non-Goals

**Goals:**
- The extraction resource accepts its `Provider` (via `Lazy[Provider]`) and never selects internally.
- Production wires the global factory once (`provide(Provider, build_selected_provider)`); bench/tests supply the provider directly.
- "No provider" uses the single `ResourceUnavailable` seam; delete `unavailable_reason` and the `None`-return contract.
- Collapse the two no-LLM branches in `_phase_extract_answer` into one.
- Remove the bench re-injection + Tier-1 `cast`; remove the ~8 test pokes.
- No external behavior change; cold start unchanged.

**Non-Goals:**
- A new `LlmService` class/protocol. `Provider` is the shared contract (Extractor + Judge already depend on it; mock providers already satisfy it). This change makes the *resource* honor that contract — nothing new is invented.
- Touching the `Judge`/`BenchJudge` construction path (they already take a `Provider` directly).
- Any change to `select_provider`'s signature, the manifest registry, or settings.

## Decisions

**D1 — `app.provide(Provider, build_selected_provider)`; resource depends on `Lazy[Provider]`.** The factory body is `select_provider(settings)`; on `None` it raises `ResourceUnavailable(reason)`. Awaiting the `Lazy[Provider]` then either yields the provider or raises `ResourceUnavailable` — identical semantics to the browser/cookie stubs.
- *Alternative rejected:* a plain `provider=` constructor kwarg (the earlier "Tier 2" framing). It works, but DI is how every other resource is wired; using it keeps `server.py` the single composition root and lets tests override `Provider` in the test app rather than passing constructors around.

**D2 — "Unavailable" is a raised `ResourceUnavailable`, not `None`/`unavailable_reason`.** Delete the property and the sentinel return. The reason string moves to the `unavailable_lazy(Provider, reason=…)` stub (bench/tests) and to `build_selected_provider`'s raise (production).
- *Consequence:* `extract()`'s contract changes from "returns `None` when unavailable" to "raises `ResourceUnavailable`." The single caller (`_phase_extract_answer`) is restructured so one `try` covers both resolution and `extract()`.

**D3 — Bench selects once, for everyone.** `_pick_provider` still returns `(provider, provider_id)` for the judges; `bootstrap_state(settings, *, provider=…)` wraps that provider as a `Lazy[Provider]` for the resource. The `AppSettings(llm_provider=provider_id)` line, the `cast("ProviderMode", …)`, and the `TYPE_CHECKING ProviderMode` import are deleted. `provider_id` survives only for the run banner.

**D4 — Tests use the injection seam.** 5 "inject a mock provider" sites become a supplied `Lazy[Provider]` (or DI override); the 3 "force unavailable" sites pass `unavailable_lazy(Provider, reason=…)`. The model-label / cache-wiring deltas from letting `_build` construct the Extractor are verified per test (single-fetch ask-tests should not observe them).

**D5 — Spike first.** Before rewiring any consumer, a throwaway test confirms: (a) `provide(Provider, f)` accepts the Protocol key; (b) a factory param typed `Lazy[Provider]` resolves; (c) a `ResourceUnavailable` raised inside the factory propagates through the `await` (not swallowed/wrapped by a2kit). If (c) fails, fall back to D1's rejected `provider=` kwarg — the rest of the design is unchanged.

## Risks / Trade-offs

- **a2kit may wrap or cache a factory exception differently than a direct `await`** → the D5 spike checks this explicitly; the `provider=`-kwarg fallback de-risks it without reworking the spec.
- **`extract()` contract flip (None → raise) ripples** → grep shows one production caller (`_phase_extract_answer`) and a handful of tests asserting `None`; all are in-scope and updated. The wire/response shape is untouched (the OperatorHint is still built, just from one site).
- **Protocol as a DI key is a new pattern in a2web** (today only concrete classes/resources are provided) → low risk given a2kit keys on `type_` generically; documented in `server.py` next to the registration.
- **`provider_id` for the banner** is no longer threaded through settings → read it straight from `_pick_provider`'s return; no behavior change.

## Migration Plan

Internal refactor, no runtime migration. Spike (D5) → rewire production (`provide` + resource) → rewire bench → migrate tests → collapse `_phase_extract_answer`. Gate on `make check` (lint + ty + test ≥85% + arch). Acceptance bar is behavior parity: the extraction + output-benchmark capability tests pass unchanged, and the no-LLM degrade still emits `llm_unavailable`. Rollback is a single revert. Picked up by the live MCP binary on the next `make install-global` (no behavior change, no urgency).

## Open Questions

- Does the DI `Provider` factory need to memoize across the app, or is a2kit's singleton scope sufficient? (Default singleton scope should make `build_selected_provider` run once; confirm in the spike.) Non-blocking — at most one redundant selection.
