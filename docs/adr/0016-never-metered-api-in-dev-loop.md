# ADR-0016 — Never bill the metered API in the dev/eval loop (dev-loop tenet)

**Status:** **Accepted** (decided 2026-07-11)
**Date:** 2026-07-11
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never silently substitute a worse path / report loudly — direct prior art for the fail-loud posture here), ADR-0001 (structural prevention over vigilance — the guard is prevention, not a checklist), openspec change `bench-cost-isolation` (full record).

> **Terminology note:** "provenance" in this ADR means *provider + model stamping in run artifacts*. It is UNRELATED to ADR-0014's URL provenance (`{{n}}` handle grounding / `off_domain`). This ADR does not touch URL grounding.

## Context

A full `make bench` billed ~$20 on a real metered Anthropic account. Root cause (grounded to file:line in the openspec change): provider selection auto-order is `claude-code → anthropic → openai_compatible` (`src/a2web/llm_resource.py:47`). In the non-interactive `make bench` shell the Claude Code OS session was **not detected**, so selection **silently fell through** to metered `anthropic`, and `eval/_prod_env.py` had merged an `ANTHROPIC_API_KEY` from `~/.claude.json`, giving the fallback a key to bill. The cost driver is the Sonnet judge (`claude-sonnet-4-6`) — ~80 judge calls across a 36-cell run.

The dev/eval/bench loop is developer-paid. Metered spend there is pure waste when subscription/cheap routing is already the default preference — and a *silent* fallthrough is the trap: money is spent without the operator choosing to.

## Decision

In the dev/eval/bench loop, LLM calls MUST NOT touch the metered Anthropic API by accident. Enforced **structurally** (ADR-0001 — prevention, not vigilance):

1. **A cost guard on the resolved `(provider, model)` pair runs before every completion.** The bench acquires its provider only pre-wrapped in that guard (`with_cost_guard`), so no un-guarded completion path exists. Rule: *expensive models only via subscription, never metered* — `claude-code` (flat subscription) may use any model; metered `anthropic` may use only cheap models (Haiku); `openai_compatible` only an explicit cheap allowlist; `anthropic:sonnet-*/opus-*`, `openai_compatible:gpt-4*`, and unknown pairs are DENIED (fail loud, opt in deliberately).
2. **Fail loud, never silent-bill.** The bench defaults `A2WEB_BENCH_PROVIDER=claude-code` and raises `LLMNotAvailable` when the session is absent, rather than falling through. Metered `anthropic` (cheap only) is reachable solely under explicit opt-in.
3. **Provenance stamping.** Every run artifact records the provider + model actually used, so a run that hit metered API is identifiable from its own artifact.

Acceptable providers for the dev/eval loop: Claude Code (CLI/SDK) subscription, opencode, codex, or a genuinely cheap model.

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / ADR-0012 / ADR-0014 precedent: a single project's dev-loop invariant belongs in a2web's `CLAUDE.md` "Never" section with rationale here, not in `CONSTITUTION.md` (verbatim a2kit-synced substrate governance).

## Consequences

- New substrate-indifferent primitive `packages/llm_cost_guard.py` (`assert_within_budget` + `CostPolicy` + `CostViolation` + `with_cost_guard`), shelf-bound (promote to `llm-cost-guard` once a second project consumes it — rule-of-three).
- `EvalReport`/`EvalRow` carry `provider`; the manifest + `results.json` stamp it.
- Per-item (`--slug`) and per-axis (`--axis`) isolation so a spike is a handful of guarded, stamped calls, not the full ~80-Sonnet matrix.

## Re-evaluation triggers

- If the model→cost policy outgrows an allowlist, adopt a price-table ceiling (USD/Mtok).
- If an `opencode` / `codex` provider lands, add it to the manifest + allow it in the policy.
- If a per-item cost/certainty signal is ever needed on the product wire, that is a separate decision (this ADR is dev-loop only).
