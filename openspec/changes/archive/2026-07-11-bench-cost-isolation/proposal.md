## Why

A full `make bench` billed **~$20 on a real metered Anthropic API account**. Investigation (this session, cited to file:line) found the cause is a **silent provider fallthrough**, not a design choice:

- The provider auto-order is `claude-code` (OAuth subscription, free) → `anthropic` (metered API) → `openai_compatible` (`src/a2web/llm_resource.py:47`). The bench already *prefers* the subscription path.
- In the non-interactive `make bench` shell the Claude Code OS session was **not detected**, so selection **silently fell through** to metered `anthropic`. `eval/_prod_env.py` had merged an `ANTHROPIC_API_KEY` from `~/.claude.json` (`eval/_prod_env.py:29-46`), giving the fallback a key to bill.
- Cost driver: the **Judge is Sonnet** (`claude-sonnet-4-6`, `src/a2web/llm_eval/__main__.py:96-100`). A full run = 12 items × 3 systems = 36 cells → **~80 Sonnet judge calls** (quality + clarity + next_links axes), each carrying the full page+answer. Systems themselves are cheap (Haiku).
- **Isolation is coarse:** only `--mode` (systems) and `--only <class>` (corpus class) exist (`__main__.py:78`, `__main__.py:101`). There is **no single-item and no single-axis** filter, so you cannot run "just this URL, just the quality axis" — you pay a whole class × all axes.

Standing rule (user, durable): **the dev/eval/bench loop must never touch the metered Anthropic API** — subscription (Claude Code CLI/SDK), opencode, codex, or a genuinely cheap model only. Metered `anthropic` is opt-in, never a silent fallback.

## What Changes

- **Hard cost assertion at the call seam (impossible-by-construction).** Every bench LLM completion SHALL pass through a guard on the resolved `(provider, model)` pair *before the call is issued*, raising `CostViolation` if the pair is not cheap-approved. The rule: **expensive models only via subscription, never metered** — `claude-code` (subscription) may use any model; metered `anthropic` may use only cheap models (Haiku); `openai_compatible` may use only an explicit cheap allowlist; `anthropic:sonnet-*/opus-*` and `openai_compatible:gpt-4*` are DENIED. The bench SHALL acquire its provider only through a factory that wraps `complete()` in this guard, so no un-guarded path exists (not merely a config check). This covers the accidental-expensive-model case (a bumped judge, a mis-pointed `openai_compatible`), not just metered Anthropic.
- **Fail-loud, never silent-bill.** Default `A2WEB_BENCH_PROVIDER=claude-code` in the `make bench` target so the subscription preference is explicit; the bench fails loud (`LLMNotAvailable`) if the session is genuinely absent rather than silently falling through to metered `anthropic`. Metered `anthropic` (cheap models only) remains reachable solely under an explicit opt-in.
- **The guard is a shelf primitive.** The cost assertion SHALL be authored as a substrate-indifferent primitive (`llm-cost-guard`: `assert_within_budget(provider, model, policy)` + model→tier table + `CostViolation`) and promoted to the shelf — it is DEEP (tiny surface, hides "what costs what"), STABLE (a forever concern), and WINS (reused by every future benchmark in every project; prevents real money loss). The broader eval harness (corpus/judge/axes/isolation) stays a2web-local until a second consumer proves its shape (rule-of-three) — but a2web's seams (provider-policy, provenance-record, isolation-filter) are kept clean so later promotion is cheap.
- **Provenance stamping.** Every bench run artifact (the dated report under `eval/runs/`, and each per-cell record) SHALL record the **provider + model actually used** (e.g. `provider=claude-code model=…` vs `provider=anthropic model=claude-sonnet-4-6`). A run that hit metered API SHALL be visible in its own artifact.
- **Per-item isolation.** Add a corpus-item filter (`--slug` / `--id`) so a single corpus item can run alone (`__main__.py` corpus filter, alongside the existing `--only <class>`).
- **Per-axis isolation.** Add per-axis skip/select flags so a run can execute a single axis (e.g. quality only), avoiding the ~80-Sonnet-call full matrix during spikes (`runner.py:289-297` currently run all axes unconditionally).
- **(Optional, net-new — scoped separately if pursued)** an `opencode` provider manifest mirroring `claude_code.py`, slotting into `_PROVIDER_ORDER`. No opencode integration exists today.

These together make the sibling `terse-query-grammar` spikes affordable: one item × one axis on the subscription provider is a handful of calls, provenance-stamped, with zero metered-API risk.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `output-benchmark`: adds fail-loud metered-API refusal, provider+model provenance stamping in run artifacts, and per-item + per-axis isolation flags.
- `provider-selection`: the bench-context selection SHALL treat metered `anthropic` as opt-in (explicit), not a silent fallback of the auto-order.

## Impact

- `Makefile` — default `A2WEB_BENCH_PROVIDER=claude-code` on the `bench`/`eval` targets.
- `src/a2web/llm_eval/__main__.py` — `--slug`/`--id` corpus filter; per-axis flags; metered-refusal guard; provenance capture into the run context.
- `src/a2web/llm_eval/runner.py` — per-axis skip wiring (`_run_one`); stamp provider+model per cell.
- `src/a2web/llm_eval/report.py` — write provider+model into the run artifact header/records.
- `src/a2web/llm_resource.py` — bench-context guard so metered `anthropic` is opt-in, not silent.
- Tests under `tests/capabilities/output_benchmark/` — cover the guard, provenance, and isolation flags.
- No product-runtime change — this is the dev/eval loop only.
