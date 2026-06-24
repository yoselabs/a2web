## Why

The "prefer claude-code, fall back to anthropic, honor an explicit pin" provider-selection policy is hand-written **twice** — in `llm_resource._build()` (production `ask` path) and `llm_eval/__main__._pick_provider()` (bench) — with divergent ceremony. The `("claude-code","anthropic")` fallback order, the `{anthropic, claude-code}` id set, and the manifest surface-path string are each restated across 2–5 sites, so adding or reordering a provider means editing several places in lockstep. Alongside it sits genuinely dead code (`ModelSpec.provider` + `.key()`, a `Literal`-narrowing ladder that only appeases the type checker). This is a no-behavior-change cleanup to collapse the duplication onto one idiomatic seam before the surface grows again.

## What Changes

- Add one module-level function `select_provider(settings, *, override=None) -> tuple[str, Provider] | None` in `llm_resource.py` (the primary consumer; `domain.py` is excluded because its "pure functions only" contract forbids the `load_surface` provider construction this does), owning the manifest load, the `("claude-code","anthropic")` order, and the explicit-pin rule. It returns `(provider_id, provider)` or `None`.
- Rewrite `llm_resource._build()` and `llm_eval/__main__._pick_provider()` to call `select_provider(...)`, keeping **only** their own error-shaping (production returns `(None, reason)`; bench raises `LLMNotAvailable` and keeps its "unknown provider id" env-override validation).
- **BREAKING (internal package API only)** Delete the dead `ModelSpec.provider` field and `ModelSpec.key()` (zero production readers; cache keys on the model string). Update the one unit test that asserts `.key()`.
- Delete the `Literal["anthropic","claude-code"]` narrowing ladder in `_pick_provider` (`str` suffices; pydantic re-validates at the `AppSettings` boundary).
- Collapse the ~5 prose copies of the "claude-code first, no API key" rationale to one docstring on `select_provider`; fix the misleading `AnthropicProvider()` `Usage:` examples in `extractor.py` / `judge.py` that lure callers into bypassing the registry.
- Add an architecture test asserting the fallback-order tuple and the `_manifests.llm_providers` surface string each appear exactly once under `src/a2web/`.
- **Out of scope (deferred):** the bench double-selection / `AppSettings(llm_provider=provider_id)` re-injection (Tier 2) — it would perturb `LlmExtractorResource`'s `Lazy[T]` lazy-construction contract and belongs in its own change.

## Capabilities

### New Capabilities
- `provider-selection`: the single domain seam that chooses an LLM provider from the manifest registry — preference order, explicit-pin override, and the `(provider_id, provider)` result contract — consumed by both the production extractor path and the bench harness.

### Modified Capabilities
<!-- None. This is a refactor: no spec-level requirement of an existing capability changes. extraction / output-benchmark behavior is preserved byte-for-byte on the wire. -->

## Impact

- **Code:** `src/a2web/llm_resource.py` (new `select_provider` fn + `_build`), `src/a2web/llm_eval/__main__.py` (`_pick_provider`), `src/a2web/packages/llm_extract/extractor.py` (`ModelSpec` field + docstring), `src/a2web/packages/llm_extract/judge.py` (docstring).
- **Tests:** update `tests/packages/llm_extract/test_llm_module.py` (`.key()` assertion); add `tests/architecture/test_provider_order_single_source.py`. Mock-provider tests that inject `_extractor`/`_unavailable_reason` directly are untouched (selector sits above that seam).
- **Behavior:** none — same provider chosen for the same inputs; MCP/CLI/bench output unchanged. No new dependency, no new top-level concept (Constitution Art. VI magic budget honored).
- **No MCP tool-signature, response-envelope, or settings change.**
