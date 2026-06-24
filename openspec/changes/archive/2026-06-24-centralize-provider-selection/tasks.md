## 1. Add the shared selector

- [x] 1.1 Add `select_provider(settings, *, override=None) -> tuple[str, Provider] | None` to `src/a2web/llm_resource.py` (module-level), with module-level `_PROVIDER_SURFACE = "a2web._manifests.llm_providers"` and `_PROVIDER_ORDER = ("claude-code", "anthropic")`. It loads the registry, resolves the pin (`override or settings.llm_provider`; `auto` → `_PROVIDER_ORDER`, else `(pin,)`), returns the first present `(name, provider)` or `None`.
- [x] 1.2 Give it the single canonical docstring for the "claude-code first, no API key" rationale (the one place this prose now lives).

## 2. Route production through it

- [x] 2.1 Rewrite `llm_resource._build()` to call `select_provider(s)`; on `None` return `(None, "no LLM provider available (…)")` preserving the existing reason wording; otherwise unpack `provider_id, provider` and build the `Extractor` as before.
- [x] 2.2 Remove the now-dead inline order tuple / membership loop and the duplicated rationale comment block from `_build()`.

## 3. Route bench through it

- [x] 3.1 In `llm_eval/__main__._pick_provider()`, keep the `A2WEB_BENCH_PROVIDER` parse + "unknown provider id" validation, then call `select_provider(settings, override=<validated id or None>)`; on `None` raise `LLMNotAvailable` with the existing message.
- [x] 3.2 Delete the `Literal["anthropic","claude-code"]` return narrowing and the two `if name == "anthropic"` branches; return `provider_id` as `str`. Adjust the `_pick_provider` signature and `_BENCH_PROVIDER_IDS` usage (keep `_BENCH_PROVIDER_IDS` only if still needed for the unknown-id validation; do not let it re-declare the fallback order).

## 4. Remove dead identity code

- [x] 4.1 Delete `ModelSpec.provider` field and `ModelSpec.key()` in `packages/llm_extract/extractor.py`; update every `ModelSpec(provider_id, model)` construction (`llm_resource.py`, `__main__.py`, and tests) to the new single-arg shape.
- [x] 4.2 Update `tests/packages/llm_extract/test_llm_module.py` to drop/replace the `.key()` assertion.
- [x] 4.3 Fix the misleading `AnthropicProvider()` `Usage:` docstring examples in `extractor.py` and `judge.py` so they don't show registry-bypassing construction.

## 5. Lock it with an architecture test

- [x] 5.1 Add `tests/architecture/test_provider_order_single_source.py` asserting the literal `("claude-code", "anthropic")` order tuple and the `"a2web._manifests.llm_providers"` surface string each appear exactly once under `src/a2web/`.

## 6. Verify behavior parity

- [x] 6.1 Run `make check` (lint + ty + test ≥85% + arch) — all green.
- [x] 6.2 Confirm the extraction + output-benchmark capability tests pass unchanged (no wire/behavior drift); spot-check `a2web web ask` and a `--mode baseline` bench dry path resolve the same provider as before.
