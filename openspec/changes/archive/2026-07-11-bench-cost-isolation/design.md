# Design — bench cost, isolation & the cost guard

## D0. ADR-0016 (draft — promote to `docs/adr/0016-*.md` on apply)

> # ADR-0016 — Never bill the metered API in the dev/eval loop (dev-loop tenet)
>
> **Status:** Proposed (drafted 2026-07-11) · **Date:** 2026-07-11 · **Supersedes:** —
> **Related:** ADR-0009 (fail-loud / never silently substitute a worse path — direct prior art for the fail-loud posture here). NOTE: "provenance" in this ADR means *provider+model stamping in run artifacts* — it is UNRELATED to ADR-0014's URL provenance; do not read this as re-opening 0014.
>
> ## Context
> A full `make bench` billed ~$20 on a real metered Anthropic account because provider selection silently fell through `claude-code → anthropic → openai_compatible` when the subscription session was undetected, and `eval/_prod_env.py` supplied a metered key. The dev/eval loop is developer-paid; metered spend there is pure waste when subscription/cheap routing is already available.
>
> ## Decision
> In the dev/eval/bench loop, LLM calls MUST NOT touch the metered Anthropic API by accident. Enforced structurally (ADR-0001 style — prevention, not vigilance): a cost guard on the resolved `(provider, model)` pair runs before every completion, and the bench acquires its provider only pre-wrapped in that guard. Expensive models are allowed only via subscription (`claude-code`); metered `anthropic` is allowed only for cheap models and only under explicit opt-in; the bench fails loud (`LLMNotAvailable`) rather than silently falling through. Acceptable providers: Claude Code (CLI/SDK) subscription, opencode, codex, or a genuinely cheap model.
>
> ## Placement
> `docs/adr/0016-*.md` + `docs/adr/INDEX.md` row + a "Never" line in `CLAUDE.md`. NOT `CONSTITUTION.md`.
>
> ## Consequences
> `llm-cost-guard` primitive (shelf-bound); provider+model provenance stamped in artifacts; metered API becomes explicit opt-in.
>
> ## Re-evaluation triggers
> If the model→cost policy grows past an allowlist (adopt a price-table ceiling); if an opencode/codex provider lands.

## D1. Root cause (grounded, this session)

`make bench` billed ~$20 because provider selection **silently fell through** the auto-order `claude-code → anthropic → openai_compatible` (`llm_resource.py:47`): the Claude Code OS session was undetected in the non-interactive shell, and `eval/_prod_env.py:29-46` had merged an `ANTHROPIC_API_KEY` from `~/.claude.json`, so the metered fallback had a key. The **Judge is Sonnet** (`__main__.py:96-100`); a full run is ~80 Sonnet judge calls across 36 cells. On subscription those calls are free; on metered API they were the $20.

## D2. The guard: assertion at the call seam, not config

```
guard_model_cost(provider_id, model_id, policy) -> None          # raise CostViolation on violation

policy (allowlist form — start here, airtight for a small set):
  claude-code    : *                 subscription: any model (Sonnet judge free)
  anthropic      : haiku-*           metered API: cheap models ONLY
  openai_compat  : {explicit cheap ids}
  DENY           : anthropic:sonnet-*, anthropic:opus-*, openai_compat:gpt-4*, unknown pairs
```

Encoded rule: **expensive models only via subscription, never metered.** Airtight-ness comes from *where* it runs: the bench obtains its provider through a factory that wraps every `complete()` in the guard —

```
guarded = with_cost_guard(select_provider(...), policy)   # every call checked, no escape path
```

so an accidentally-bumped judge model or a mis-pointed `openai_compatible` raises **before spending a cent**. This is stronger than "refuse metered anthropic": it guards the resolved model, whatever the provider.

Allowlist now; a model→USD/Mtok price-table with a ceiling is the natural evolution once the set of models grows (defer until needed).

## D3. Shelf split (rule-of-three)

```
PROMOTE now  →  llm-cost-guard   (shelf primitive)
   assert_within_budget(provider, model, policy) · model→tier table · CostViolation · with_cost_guard(provider)
   DEEP (tiny, hides cost knowledge) · STABLE (forever concern) · WINS (every bench, every project)
   Proven pain ($20). This is the nucleus of the "accumulated benchmark experience" the user wants.

DEFER      →  bench-kit / eval-harness (corpus runner · judge · axes · provenance · isolation)
   Only ONE consumer today (a2web); corpus shape / four axes / systems still domain-coupled.
   Wait for a second project (rule-of-three) before freezing the harness shape.
   BUT keep a2web's seams promotable: provider-policy, provenance-record, isolation-filter.
```

Follow the shelf loop (`<shelf>/docs/agent-loop.md`) at *build* time, not now — this change captures the decision, not the promotion.

## D4. Provenance

Every run artifact (`eval/runs/<date>...`) and each per-cell record stamps the resolved `provider` + `model` (the pair the guard approved). A metered run is visible in its own artifact; a cross-run quality comparison is only trustworthy when every cell shares the stamped pair. This is the record half of the guard.

## D5. Isolation (what enables cheap spikes)

Today: `--mode` (systems) + `--only <class>` (corpus class) only (`__main__.py:78`, `:101`). No single-item, no single-axis. Add:

- **`--slug` / `--id`** corpus-item filter (finer than `--only <class>`) — run one URL alone.
- **per-axis select/skip** — axes run unconditionally at `runner.py:289-297`; add flags so a spike runs e.g. quality only.

Result: a `terse-query-grammar` spike = 1 item × 1 axis on the subscription provider = a handful of guarded, stamped calls — not the ~80-Sonnet full matrix.
