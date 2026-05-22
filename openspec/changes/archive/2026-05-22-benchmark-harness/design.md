## Context

`src/a2web/llm_eval/` is a working, typed harness: `load_corpus` → `EvalSuite` matrix runner → `Judge` → `report.write_all`, with three systems (`WebFetchBaseline`, `A2WebDetail`, `A2WebExtract`). It is invoked by `python -m a2web.llm_eval` / `make eval`. Two gaps make it not yet a *benchmark*: it scores only answer quality (no token-cost, clarity, or contract axes), and `__main__.py` hardcodes `AnthropicProvider()` so it needs `ANTHROPIC_API_KEY`. Its default corpus still points at the dead `benchmarks/vs-webfetch/2026-05-11/`. This change closes those gaps in place rather than starting over.

## Goals / Non-Goals

**Goals:**
- A benchmark that re-runs unchanged across future envelope versions — typed, covered by tests, package-resident.
- Four axes per (URL, system): answer quality, token cost, output clarity, data-contract conformance.
- A `next_links_picked_correctly` axis on listing URLs.
- A tricky-scenario corpus: Reddit comment threads, HN comment/item pages, index/listing pages.
- One command, no API key (`claude-code` provider), automated vs-WebFetch comparison.

**Non-Goals:**
- No change to a2web product behavior, the wire envelope, or dependencies.
- Not a latency benchmark — wall time is recorded but not a scored axis (it is environment-dependent).
- No new judge model or multi-model sweep (the old harness's `multi_model.py` experiment is not revived).

## Decisions

### Extend `llm_eval`, not new `benchmarks/` scripts

The benchmark becomes part of the package: typed, `ty`-checked, test-covered, imported like any module. **Rationale:** today's failure is precisely that the benchmark lived as dated throwaway scripts outside the package and rotted three envelope versions deep before anyone noticed. A re-runnable benchmark must be maintained, and only package-resident code is maintained here. *Alternative considered:* a fresh `benchmarks/<date>/` dir — rejected; it reproduces the exact rot this change exists to end.

### Data-contract conformance is deterministic, not judged

Three axes (quality, clarity, next_links) need an LLM judge. The fourth — data-contract conformance — is a **programmatic** assertion over the a2web envelope: `tier`/`url`/`status` present only when deviating, `debug` present only under `debug=True`, `next_links` well-shaped. **Rationale:** a contract is binary and exactly specified; an LLM judge would add cost, latency, and nondeterminism to a check that is a plain assertion. It also means contract regressions fail the benchmark hard, like a test. *Alternative:* fold it into the judge prompt — rejected (a contract is not a matter of opinion).

### Token cost measures the envelope, not the LLM call

`EvalRow` already carries `fetch_prompt_tokens` / `fetch_completion_tokens` — those are *LLM-call* tokens. The benchmark's token axis is the size of the **a2web response envelope** an agent must read: a per-field token breakdown (`content_md`, `links`, `next_links`, `diagnostics`, `debug`, …). Carried in `SystemResult.metadata` and surfaced as its own `EvalRow` field. WebFetch's token axis is the size of its returned text.

### Provider: `claude-code` preferred, no API key

`__main__.py` switches from a hardcoded `AnthropicProvider()` to provider selection that prefers `ClaudeCodeProvider` (OAuth subscription) and falls back to `AnthropicProvider` only when `claude-agent-sdk` is unavailable — overridable via an env var. The judge and the `A2WebExtract` reader both run on the subscription; no `ANTHROPIC_API_KEY` required.

### Corpus home and the vs-WebFetch baseline

The corpus moves to a stable in-repo path (`eval/corpus.yaml`); `_DEFAULT_CORPUS` repoints there. `WebFetchBaseline` is already a faithful in-process reproduction of Claude Code's WebFetch, so the head-to-head runs fully automated — no interactive phase, contrary to the old harness's manual Phase 2.

## Risks / Trade-offs

- **Live sites rate-limit or rotate content (Reddit / HN / PyPI)** → corpus `criteria` are phrased against stable structural facts ("identifies ≥5 stories", not "the top story is X"); fetch errors are recorded as a distinct outcome, not scored as a quality 0.
- **LLM judge nondeterminism** → judge model pinned; scoring is criteria-anchored; raw judge reasoning is persisted in the report so a surprising score is auditable.
- **`claude-code` provider unavailable in some environments** → explicit fallback to `AnthropicProvider` with a clear message; the env-var override lets CI force a provider.
- **The benchmark itself rotting again** → it is now covered by tests in `tests/capabilities/` (corpus loads, the contract-conformance checker, axis wiring), so an envelope change that breaks it breaks `make check`.

## Migration Plan

1. Add the corpus at `eval/corpus.yaml` with the tricky-scenario entries; repoint `_DEFAULT_CORPUS`.
2. Add the token-cost, clarity, contract, and next_links axes through `SystemResult` → `EvalRow` → `EvalReport` → `report.py`.
3. Switch `__main__.py` to claude-code-preferred provider selection.
4. Add a `make bench` target; retire the stale `benchmarks/vs-webfetch/2026-05-11/` scripts (keep `findings_*.md` as history).
5. Run the suite once; commit the dated report and a short findings summary.

Rollback: the change is additive to `llm_eval` plus a corpus file — revert the commit.
