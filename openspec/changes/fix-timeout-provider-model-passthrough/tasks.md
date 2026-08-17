## 1. Fix TimeoutProvider

- [x] 1.1 Add `__getattr__` to `TimeoutProvider` (`src/a2web/llm_resource.py`) forwarding unknown attributes to `self.inner`, guarded against recursion during `__init__` (read `inner` via `object.__getattribute__` inside `try/except AttributeError`, not `self.inner` directly)
- [x] 1.2 Confirm `TimeoutProvider.name`/`available()` stay explicit dataclass members (unaffected — normal attribute lookup finds them before `__getattr__` is ever consulted)

## 2. Regression test

- [x] 2.1 Add a test (extending `tests/capabilities/app_composition/test_llm_timeout.py` or `tests/packages/llm_extract/test_openai_compatible_selection.py`) that configures the `openai-compatible` backend with an explicit `OPENAI_MODEL`, calls `select_provider()`, and asserts `.default_model` on the real returned (wrapped) provider equals the configured model — not a bare/unwrapped adapter
- [x] 2.2 Add a test asserting `LlmExtractorResource._build()` (or an equivalent end-to-end path) resolves `ModelSpec` to the openai-compatible model, not `s.llm_model`, when going through the real `select_provider()` return value

## 3. Documentation

- [x] 3.1 Add footgun #9 to `LESSONS_LEARNED.md`, matching the existing entry format (problem statement, root cause, impact, fix, regression test reference) — cross-reference footgun #1 as the related-but-distinct provider-order leak
- [x] 3.2 In the footgun entry, note that `anyllm.cost.with_cost_guard`'s `_GuardedProvider` does not share this gap (it already has `__getattr__`) and that it is not currently composed into `select_provider()`'s chain

## 4. Verification

- [x] 4.1 Run `make check` (lint + ty + test, coverage ≥85%) — 1892 passed, 92.14% coverage, all clean
- [x] 4.2 Manually confirm via the existing `test_the_wrap_happens_at_the_seam`-style assertion that `select_provider()` still returns a `TimeoutProvider` satisfying the `LLMProvider` protocol (no regression to the timeout bound itself) — `test_llm_timeout.py::test_the_wrap_happens_at_the_seam` passed unchanged
