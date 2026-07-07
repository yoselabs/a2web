## Why

The bench is live-network and spends LLM quota (on the claude-code subscription
by default), so running the full 22×3 matrix is expensive. Two things make a
cheap, honest run possible: (1) a machine-readable per-run results file with the
real token/cost totals the SDK already reports, so a run's spend is legible
without re-deriving it from markdown; (2) a way to run only the crucial cells.
Plus, this session shipped answer neutrality on selection questions — but the
corpus has no "which is best?" case, so a bench run wouldn't even exercise it.

Most of the plumbing already exists (cost/tokens are captured from the SDK's
`ResultMessage`; `results.tsv` + `manifest.json` + `cost.md` are written; a
subset corpus + `--mode detail` already narrow a run). This change closes the
three specific gaps, small and code-only.

## What Changes

- **`results.json` per run** — a structured file with one object per (corpus ×
  system) cell (scores + `fetch_cost_usd` / token counts / `judge_cost_usd`) plus
  a run **summary** rolling up `total_cost_usd` and total prompt/completion tokens
  (overall and per-system). The token/cost values are the ones the claude-code SDK
  already reports; this just persists them as JSON, not only TSV/markdown.
- **`--only <class>` subset filter** — run only the corpus cases of a given class
  (e.g. `--only listing`), so a crucial run costs a fraction of the full matrix
  without hand-maintaining a subset corpus file.
- **One selection-question corpus case** — a "which is best?" task over a listing,
  so the bench actually exercises the answer-neutrality behavior (ADR-0012): the
  answer must present options + criteria and not crown an a2web-manufactured best.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `output-benchmark`: the benchmark SHALL emit a structured `results.json` (per-cell
  rows + a cost/token run summary) and SHALL accept an `--only <class>` filter to
  run a subset of the corpus.
- `eval-corpus`: the corpus SHALL include a selection-question case (a "which is
  best?" task over a listing) that exercises answer neutrality.

## Impact

- **Code**: `src/a2web/llm_eval/report.py` (write `results.json` + summary),
  `src/a2web/llm_eval/__main__.py` (`--only` arg + corpus filter),
  `eval/corpus.yaml` (one selection case). Tests under
  `tests/capabilities/output_benchmark/` with stubs — no live LLM calls.
- **No product-wire change**; harness-only. `make check` unaffected (the four-axis
  harness tests keep running with stubs); `make bench` remains opt-in.
- **Cost**: building + testing this is stub-driven (no bench spend). Running the
  bench stays the user's explicit, budget-gated choice.
