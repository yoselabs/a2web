## Why

`TimeoutProvider` (`src/a2web/llm_resource.py:248-282`) wraps every provider `select_provider()` returns — unconditionally in production, since `llm_timeout_s` defaults to `180.0`. It forwards `.name` and `.available()` to `self.inner` but has no `default_model` property and no `__getattr__` passthrough. `_build()` reads the model id back via `getattr(provider, "default_model", "") or s.llm_model` (`llm_resource.py:354`); the `getattr` always misses on the wrapped instance, so every extraction call falls through to `s.llm_model` — the hardcoded Anthropic default `claude-haiku-4-5-20251001` — even when `openai-compatible` correctly resolved its model from `OPENAI_MODEL`. Confirmed live: a deploy with `OPENAI_MODEL` and `A2WEB_LLM_PROVIDER=openai-compatible` set correctly still sent the Anthropic model id to the configured gateway on every call, which the gateway cannot route, producing `llm_error` with an empty answer.

This is the same class of footgun as `LESSONS_LEARNED.md`'s "Default model is metered Anthropic" entry, but a distinct leak: that one was a provider-*order* leak (fixed by reordering `auto`); this is a wrapper-*attribute* leak that fires even when the order is already correct, and existing tests never caught it because they assert on `.name`/`.available()` through the wrap, never on `.default_model`.

## What Changes

- Add `__getattr__` passthrough to `TimeoutProvider`, forwarding any attribute the wrapped provider defines (mirrors `anyllm.cost._GuardedProvider`'s existing pattern for the same wrapper shape) — closes the whole class of "wrapper silently drops a provider attribute" bug, not just this one field.
- Add a regression test asserting `select_provider()`'s real, wrapped return value exposes `default_model` end-to-end for the `openai-compatible` backend — extending the existing seam tests in `tests/capabilities/app_composition/test_llm_timeout.py` / `tests/packages/llm_extract/test_openai_compatible_selection.py`, which today only assert `.name`.
- Document the bug as a new footgun entry in `LESSONS_LEARNED.md`, in the existing entry format (problem, root cause, impact, fix, regression test reference).
- Confirm (and note in the footgun entry) that `anyllm.cost.with_cost_guard`'s `_GuardedProvider` does not share this gap — it already has `__getattr__` — and that it is not currently composed into `select_provider()`'s chain, so no second wrapper needs the same fix today.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `openai-compatible-provider`: the "Model resolution with curated recommendations, fail-loud on unknown" requirement already states the resolved model SHALL NOT fall back to the Anthropic default; this adds a scenario making explicit that the resolution SHALL survive `select_provider()`'s own wrapping (e.g. the timeout bound), not just hold at provider-construction time — the gap this change fixes.

## Impact

- `src/a2web/llm_resource.py` — `TimeoutProvider` class only; no signature or protocol change, no new dependency.
- `LESSONS_LEARNED.md` — new footgun entry.
- Test suite — one new/extended regression test near the two files named above.
- No settings, env var, or public API surface changes.
