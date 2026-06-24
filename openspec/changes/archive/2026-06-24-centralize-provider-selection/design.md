## Context

Provider selection lives at two layers today. The **manifest registry** (`load_surface("a2web._manifests.llm_providers", Provider, settings)`) handles *discovery + capability gating* cleanly: one file per provider, unconfigured backends drop out as `Unavailable`. On top of it sits a *selection policy* — "prefer claude-code, fall back to anthropic, honor an explicit pin" — and that policy is hand-written twice:

- `llm_resource._build()` (prod `ask` path): reads `settings.llm_provider`; `auto → ("claude-code","anthropic")`, else `(settings.llm_provider,)`; first-present wins; returns `(None, reason)` on miss.
- `llm_eval/__main__._pick_provider()` (bench): `_BENCH_PROVIDER_IDS = ("claude-code","anthropic")` + an `A2WEB_BENCH_PROVIDER` env override; first-present wins; **raises** `LLMNotAvailable` on miss; hand-narrows the result to `Literal["anthropic","claude-code"]`.

The registry cannot absorb this policy itself: `load_surface` returns a `dict` whose iteration order is alphabetical (anthropic-first) — the *opposite* of the auto preference — and the framework's `priority` axis can model auto ranking but not the explicit-pin mode. So selection genuinely needs a small caller-side function; it just needs to exist **once**.

Constraints: package modules may not import `a2web.<domain>`, so a settings-reading selector must live domain-side. Constitution Art. VI (magic budget) forbids a new class/DSL for something expressible in a few lines of plain Python. Many tests inject a pre-built `Extractor` directly onto `LlmExtractorResource._extractor`, bypassing `_build()`/`load_surface` entirely — the selector sits *above* that seam and must not disturb it.

## Goals / Non-Goals

**Goals:**
- One domain function owns the preference order, the explicit-pin rule, and the surface path.
- Both call sites delegate to it, retaining only their own error-shaping.
- Remove dead identity code (`ModelSpec.provider`, `ModelSpec.key()`, the `Literal` ladder) and collapse the duplicated rationale prose.
- Lock the single-source-of-truth with an architecture test.
- Zero behavior change: same provider chosen for the same inputs; identical MCP/CLI/bench output.

**Non-Goals:**
- The bench double-selection / `AppSettings(llm_provider=provider_id)` re-injection (Tier 2). Removing it means letting `LlmExtractorResource` accept a pre-resolved provider, which perturbs its `Lazy[T]` cold-start contract — a production seam change that belongs in its own proposal.
- Changing the manifest framework, adding a provider, or touching `priority`.
- Any MCP tool-signature, response-envelope, or settings change.

## Decisions

**D1 — One function, not a class.** `select_provider(settings, *, override=None) -> tuple[str, Provider] | None` in `domain.py`. Mirrors the repo's established "ordered preference among plugins" idiom (`TIER_ORDER` tuple + `match_handler` first-hit loop) and stays under the magic budget.
- *Alternatives rejected:* a `ProviderSelector` class / decorator (Art. VI "no Clean-Architecture cosplay"); pushing auto-order into manifest `priority` (can't express explicit-pin, and couples a per-manifest constant to a settings policy — confirmed by the registry-seam analysis).

**D2 — Home is `llm_resource.py` (module-level function).** `domain.py` was the first instinct, but its module contract is "Pure functions only. No I/O" — and `select_provider` calls `load_surface`, which imports manifests and constructs providers (env reads for API-key availability). That is not pure, so `domain.py` is the wrong home by its own stated rule. `llm_resource.py` is the primary consumer, already the production selection site (`_build`), and makes no purity claim; `_build` becomes a thin caller and bench imports the same module-level `select_provider`. No new file (`NEVER create files unless necessary`).
- *Alternatives rejected:* `domain.py` (violates its purity contract, above); a dedicated `provider_select.py` (a new module for one short function fails the minimalism test — `llm_resource.py` already owns this concern).

**D3 — Result is `(provider_id: str, Provider)`, plain `str`.** `provider_id` is the manifest name (already the canonical id; `provider.name` has spelling drift and is not consulted). The `Literal["anthropic","claude-code"]` is dropped — it was pure type-checker appeasement; pydantic re-validates the value at the `AppSettings` boundary, and bench keeps its runtime "unknown provider id" check on the env override before calling the selector.

**D4 — Selector owns `load_surface`; callers own error channel.** Passing `settings` (not a pre-built registry) lets the function own the surface-path string too (kills that duplication). Prod adapts `None → (None, reason)`; bench adapts `None → raise LLMNotAvailable`. The two error contracts are legitimately different (silent degrade-to-OperatorHint vs. exit-code-3) and stay caller-side.

**D5 — Delete `ModelSpec.provider` + `.key()`.** Zero production readers; the cache keys on the model-id string; `.key()` is exercised only by one unit test, which is updated/removed. Honors "no redundancy."

**D6 — Architecture test as the ratchet.** A new test asserts the fallback-order tuple and the surface string each appear once under `src/a2web/`, so the duplication cannot silently return — consistent with the repo's "adding a rule = writing a test" convention.

## Risks / Trade-offs

- **Bench env-override behavior could regress** (the "unknown provider id" vs "not in registry" messages) → keep the env-override parse + validation inside `_pick_provider`; only the first-present pick moves into `select_provider`. Cover both message paths with the existing bench tests.
- **`domain.py` calling `load_surface` slightly widens its import surface** (manifests → providers) → call-time only, no import-time cost; `domain.py` is already domain-coupled, so no boundary rule is crossed.
- **Deleting `ModelSpec.provider` touches the package public surface** → it is an internal dataclass field with no external consumer; the package boundary `__all__` is unaffected (the symbol exported is `ModelSpec`, not its fields). One test updated.
- **The arch-test regex could be brittle** (matching the order tuple) → anchor it on the literal `("claude-code", "anthropic")` sequence and the exact surface string, with a short allowlist comment if a second legitimate mention ever appears (the repo's grandfathering convention).

## Migration Plan

Pure internal refactor, no runtime migration. Land behind `make check` (lint + ty + test ≥85% + arch). Behavior parity is the acceptance bar: the extraction and output-benchmark capability tests must pass unchanged. Rollback is a single revert — no data, config, or wire surface is touched. The live MCP binary picks it up on the next `make install-global` (no urgency; no behavior change).

## Open Questions

- None blocking. Tier 2 (re-injection removal) is explicitly deferred to a follow-up change and noted in the proposal's out-of-scope.
