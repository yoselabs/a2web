## Context

The bench already captures real per-call cost + tokens (the claude-code provider
reads `ResultMessage.total_cost_usd` + `usage`) and writes `results.tsv`,
`manifest.json`, and `cost.md`. What's missing for a budget-conscious workflow is
(a) a single machine-readable results file with the run's spend rolled up, (b) a
built-in subset filter, and (c) a corpus case that actually tests the neutrality
change. All three are small and stub-testable.

## Goals / Non-Goals

**Goals:** structured `results.json` with a cost/token summary; a `--only <class>`
subset filter; one selection-question corpus case. Harness-only, no live LLM calls
to build or test.

**Non-Goals:** changing product wire; reworking the existing TSV/markdown outputs
(they stay); a per-URL/`--slug` filter (class filter covers the need); pricing
tables (cost comes from the SDK, not a local table).

## Decisions

**D1 — `results.json` alongside the existing outputs, not replacing them.**
Add a new artifact; keep `results.tsv` / `manifest.json` / `cost.md`. Shape: `{
"summary": {total_cost_usd, prompt_tokens, completion_tokens, per_system: {...}},
"rows": [ {slug, system, class, quality, clarity, contract_ok, fetch_cost_usd,
fetch_prompt_tokens, fetch_completion_tokens, judge_cost_usd, ...}, ... ] }`.
Rationale: one file gives a run's spend + every result to any downstream tool
without parsing markdown. *Alternative rejected:* per-cell JSON files — more files,
no benefit over one array.

**D2 — `--only <class>` filters the loaded corpus before the matrix runs.**
Filter `corpus` by the case `class` field (listing / comments / clean / gated /
spa) right after `load_corpus`. `--only` absent → full corpus (unchanged). An
unknown class → empty run + a clear message (not a crash). *Alternative rejected:*
a separate subset corpus file — the `--corpus` flag already allows that; `--only`
removes the maintenance burden.

**D3 — One selection-question case, class `listing`.**
Add a corpus case whose task is a "which is best?" selection over a listing (a
stable, low-cost page), with expectations asserting the answer presents options /
criteria and does not assert an unqualified single "best" (per ADR-0012). It rides
the existing four-axis scoring; it exists so a future bench run exercises the
neutrality change at all. *Alternative rejected:* a commerce page like Hepsiburada —
geo/proxy-flaky and heavy; pick a stable listing already in reach.

## Risks / Trade-offs

- **[results.json drifts from results.tsv]** → both derive from the same
  `EvalReport.rows`; a test asserts row count + a spot field match across the two.
- **[--only class typo silently runs nothing]** → emit a clear "0 cases match class
  X (known: …)" message and exit non-zero, so an empty run is never mistaken for a
  pass.
- **[selection case is LLM-judged, non-deterministic]** → it feeds the informational
  `make bench` axes, not the deterministic `make check` gate; no flakiness in CI.

## Migration Plan

Additive harness outputs + one CLI flag + one corpus case. No product change, no
migration. Rollback = revert. `make check` stays green (stub tests). `make bench`
optional as before.

## Open Questions

- Which stable listing URL hosts the selection case — reuse an existing corpus
  listing (e.g. a trending/index page) with a "best" task, vs. add a new URL. Lean:
  reuse an existing in-reach listing to avoid a new flaky fetch.
