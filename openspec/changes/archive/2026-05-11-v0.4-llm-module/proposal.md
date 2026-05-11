# v0.4 — `a2web.llm` module

## Why

The v0.3 envelope diet cut a2web's default per-fetch context cost from ~6,300 to ~1,300 tokens. Claude Code's `WebFetch` ships ~80–500 tokens (NL answer only). The remaining gap — and the entire reason `WebFetch` is so context-light — is that **WebFetch runs a small fast model (Haiku 4.5) over the fetched markdown server-side and returns only the answer**. The main agent never sees the page. Reverse-engineering of the Claude Code binary documents this exactly (research `~/Documents/Knowledge/Researches/123-claude-code-webfetch-internals/`): empty system prompt, no tools, single turn, 100 KB markdown cap, hardcoded user-prompt template.

a2web should offer the same trick as a first-class capability. Adding an `ask` parameter to `fetch` lets the caller pass a question; a2web runs an LLM extractor server-side over the (already-fetched-by-a-superior-pipeline) content and returns a tiny answer envelope. Callers who want the raw envelope still get it — the new behavior is opt-in.

Beyond parity with WebFetch, the v0.4 module also crystallizes a second capability the benchmark already proved valuable: **LLM-as-judge for evaluations**. The 2026-05-11 benchmark used an ad-hoc judge (`claude_p` subprocess + regex JSON parsing); v0.4 elevates that into a proper module primitive with provider abstraction, so the same judge runs against any LLM in a model matrix.

The combination unlocks a deterministic eval harness:

```
   make eval
   → runs the corpus against WebFetchBaseline + a2web-detail + a2web-extract
      × (Haiku 4.5, Sonnet, OpenRouter:DeepSeek, OpenRouter:Qwen, …)
   → judges each answer against criteria with the same Sonnet 4.6 judge
   → writes a dated leaderboard.md, cost.md, findings.md
```

WebFetchBaseline does NOT call Claude Code. It uses Anthropic API directly with the **exact prompt template, model, and constants from the research** — empty system, Haiku 4.5, 100 KB cap, identical Rb9 user-prompt. This makes WebFetch's behavior reproducible in CI without needing a Claude Code session.

The module lives at `src/a2web/llm/` alongside `cache/`, `gate/`, `browser/` — same repo, same install, same conventions. LLM dependencies are gated behind an optional `[llm]` extra so the no-key install path stays clean (vendor-neutral / air-gapped use cases unaffected).

## What Changes

**New module `src/a2web/llm/`:**

- `extractor.py` — `Extractor(model, template)` runs an LLM over `content_md + ask`. Returns `ExtractionResult{answer, model, prompt_tokens, completion_tokens, cost_usd, latency_ms}`.
- `judge.py` — `Judge(model)` scores an answer against criteria. Returns `JudgeVerdict{scores, overall, reached, reasoning, cost_usd}`. Used in evals and by any future internal quality gate.
- `cache.py` — extraction-answer LRU keyed on `(content_hash, ask_hash, model_id)`. Mirrors WebFetch's 15-min TTL by default; configurable. Sqlite-backed alongside the existing HTTP cache.
- `providers/` — `base.py` Provider Protocol; `anthropic.py` (Haiku, Sonnet) is the only provider in v0.4. OpenRouter is v0.5.
- `prompts.py` — frozen prompt templates, each with an explicit name and version (`WEBFETCH_DEFAULT_v1` = the verbatim research-derived template; `TERSE_v1` = a custom shorter variant; `JUDGE_v1` = the verdict scorer).
- `eval/` — corpus loader, system adapters (`WebFetchBaseline`, `A2WebDetail`, `A2WebExtract`), matrix runner, report generator.
- `__main__.py` — `uv run python -m a2web.llm.eval` runs the eval suite.

**Wire-in to existing modules:**

- `src/a2web/routers.py` — `fetch` tool gains optional `ask: str | None = None` param.
- `src/a2web/fetcher.py` — after the existing extract phase, when `ask` is set AND an LLM provider is configured, dispatch the extraction phase and populate `FetchResponse.extracted_answer: str | None`.
- `src/a2web/models.py` — add `FetchResponse.extracted_answer: str | None = None`; add `FetchResponse.extraction: ExtractionMeta | None = None` (model used, tokens, latency, cache hit).
- `src/a2web/settings.py` — `llm_provider`, `llm_model`, `llm_api_key_env`, `extraction_cache_ttl_s`, `extraction_max_chars` (default 100_000, matching WebFetch).
- `src/a2web/state.py` — lazy `llm_client` singleton; `None` when the `[llm]` extra is not installed OR no key is configured.

**Packaging:**

- `pyproject.toml` — new optional dep group: `llm = ["anthropic>=0.50", "openai>=1.40"]` (OpenAI SDK is OpenRouter-compatible; reserved for v0.5).
- The `llm/` module imports SDKs at function call time (or behind module-load `try/except ImportError`) so missing extras = `LLMNotAvailable` with an actionable hint, not an import crash.

**Makefile:**

- `make eval` — quick run (current corpus, single model, write report).
- `make eval-full` — full matrix (corpus × all configured systems × all configured models).
- `make eval-baseline` — WebFetchBaseline only, for drift detection.

**Migration of benchmark code:**

- `benchmarks/vs-webfetch/2026-05-11/judge.py` → `src/a2web/llm/eval/judge.py` (becomes a thin wrapper around `Judge`).
- `benchmarks/vs-webfetch/2026-05-11/corpus.yaml` stays at the benchmarks/ path; `eval/corpus.py` provides a loader that takes a corpus path.
- `benchmarks/vs-webfetch/2026-05-11/runner.py` + `aggregate.py` collapse into `eval/runner.py` + `eval/report.py`.

## Impact

**Affected specs:**
- NEW: `llm-extraction` — Extractor primitive, prompt templates, provider protocol, cache.
- NEW: `llm-judge` — Judge primitive, verdict shape.
- NEW: `llm-eval` — EvalSuite, WebFetchBaseline (faithful reproduction), system adapters, report shape.
- `tier-pipeline` (delta) — `fetch` tool gains `ask` param; `FetchResponse` gains `extracted_answer` + `extraction` fields.

**Affected code:** see "Wire-in" above.

**Breaking? No.** `ask` is opt-in. `extracted_answer` defaults to `None`. Existing callers see no shape change.

**New dependencies:** behind `[llm]` extra. Core install unchanged.

**Cost characteristics (informational, not requirements):**
- Haiku 4.5 extraction over a ~10 KB markdown body: ~$0.001 per fetch.
- Sonnet 4.6 judge call: ~$0.005 per scored answer.
- Extraction-cache hit: $0.
- Full 20-URL × 4-system × Haiku eval: ~$0.40.

## Non-goals

- **OpenRouter / non-Anthropic providers** — v0.5.
- **Schema-shaped extraction (`schema=` param)** — v0.5 with structured-mode.
- **MCP Resource pattern for big-payload handoff** — separate future work; not blocked by v0.4.
- **WebFetch-via-Claude-Code-SDK live baseline** — not needed; we reproduce WebFetch faithfully using the research-derived prompt template instead.
- **Streaming extraction output** — single-shot is the WebFetch model and matches our cost / latency targets.
- **Eval matrix CI publication** — eval runs locally and writes dated artifacts; CI integration is a follow-up once v0.4 lands.
