# a2web extraction-backend model benchmark

**Question this answers:** which LLM should power a2web's server-side `ask`
extraction? We want the **closest quality to the reference (`claude-haiku-4.5`)
at the lowest cost** — a model that matches Haiku's answer quality *and* output
clarity while undercutting its price.

This is a **reference experiment**: re-run it every couple of months, and after
any change to the extraction prompt or the router-shape parser (the
"prescription"). Each run writes a provenance-stamped result to `results/` so
runs stay comparable over time.

## What it measures

Every candidate runs the full a2web output bench (`a2web.llm_eval`, the
`a2web_extract` system) over a fixed corpus, scored on:

| Axis | Meaning | Notes |
|---|---|---|
| **quality** | is the answer correct/complete for the task? | LLM-judged 0–5 vs the corpus rubric |
| **contract** | valid a2web router-shape JSON (closed enums, `next_links`)? | the **floor** — must be N/N |
| **clarity** | is the answer clean/actionable, no preamble/noise? | LLM-judged 0–5; **sensitive to the prompt/parser** |
| **next_links** | right drilldown set on listing pages? | often handler-driven → weak differentiator |
| **cost** | extraction $ over the corpus | captured tokens × live OpenRouter price |

A **fixed strong judge** (`claude-sonnet-4.6`) scores every candidate, blind to
which model produced the output — a candidate never judges itself. All
candidates are reached through **one OpenAI-compatible endpoint** (OpenRouter),
varying only the model, so a single key sweeps the field and OpenRouter reports
per-call cost.

## Files

- `models.yaml` — candidate set + fixed judge + reference (edit to add/retire models).
- `corpus.yaml` — the committed URL set (reliably-fetchable across content classes, so this measures *model* quality, not fetch flakiness).
- `run.py` — **methodology as code**: runs the bench per candidate, aggregates four-axis scores + cost, writes `results/<date>.{json,md}`.
- `results/<date>.json` — the durable trace: provenance (a2web version, git sha, judge, prescription note) + a price snapshot + the per-model leaderboard.
- `results/<date>.md` — human-readable leaderboard.
- `runs/` — raw per-cell bench output (gitignored; regenerable).

## Re-run

```bash
OPENAI_API_KEY=<openrouter-key> \
OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
A2WEB_BENCH_PRESCRIPTION="post <change-name>: <what changed in prompt/parser>" \
uv run python eval/model_benchmark/run.py --date 2026-07-05
```

Secrets are env-only — nothing is written to the repo but the aggregate result.
`--skip-run` re-aggregates an existing `runs/<date>` without re-calling models.

## How to read a result

1. **Contract must be N/N.** A model that can't emit valid router-shape JSON is
   disqualified regardless of quality.
2. **Clarity moves with the prescription.** A low clarity score can be a *parser*
   artifact (the model emits valid content in a shape a2web mis-splits), not a
   model weakness — verify before rejecting a model on clarity alone. Record what
   the prescription was (git sha / note) so a clarity change is attributable to a
   model vs a prompt/parser change.
3. **Rank on quality-closest-to-reference under reference-cost**, using clarity
   as the tie-breaker (clean output is a2web's whole value proposition).
