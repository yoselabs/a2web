# v0.4 — `a2web.llm` module: tasks

## 1. Module scaffolding

- [ ] 1.1 Create `src/a2web/llm/` with `__init__.py` exposing `Extractor`, `Judge`, `ModelSpec`, `PromptTemplate` as the public surface.
- [ ] 1.2 Create `src/a2web/llm/providers/{base.py,anthropic.py,__init__.py}`. Define `Provider` Protocol + `ProviderResponse` dataclass in `base.py`.
- [ ] 1.3 Create `src/a2web/llm/prompts.py` with `WEBFETCH_DEFAULT_V1`, `TERSE_V1`, `JUDGE_V1` as frozen `PromptTemplate` dataclasses.
- [ ] 1.4 Create `src/a2web/llm/extractor.py` — `Extractor` class wired to a Provider.
- [ ] 1.5 Create `src/a2web/llm/judge.py` — `Judge` class wrapping Extractor + JUDGE_V1.
- [ ] 1.6 Create `src/a2web/llm/cache.py` — sqlite-backed `ExtractionCache` (same db file as HTTP cache, separate table).
- [ ] 1.7 Add `[llm]` optional dependency group to `pyproject.toml` with `anthropic>=0.50, openai>=1.40`.
- [ ] 1.8 Guard all anthropic SDK imports with `try/except ImportError`; raise a clear `LLMNotAvailable` when usage is attempted without the extra installed.

## 2. WebFetchBaseline (the eval anchor)

- [ ] 2.1 Implement `WebFetchBaseline.fetch(url, ask)` in `src/a2web/llm/eval/systems.py`. Uses our existing `httpx` for the HTTP GET (axios-equivalent).
- [ ] 2.2 Implement HTML→markdown via `markdownify` (or `html2text`). Apply 1 MiB input cap matching `om7`.
- [ ] 2.3 Truncate the markdown to 100,000 chars matching `BD_`.
- [ ] 2.4 Submit `WEBFETCH_DEFAULT_V1` to the anthropic provider with `model="claude-haiku-4-5-20251001"`, `system=[]`, `thinking_disabled=True`, `tools=None`.
- [ ] 2.5 Document Turndown-vs-markdownify rendering divergences. Pick `markdownify` if parity within reason; otherwise add a Node subprocess fallback (`turndown_js.py`).
- [ ] 2.6 Add a smoke test that runs `WebFetchBaseline` against `https://en.wikipedia.org/wiki/Rust_(programming_language)` and asserts the answer contains "Graydon Hoare" and "borrow checker".
- [ ] 2.7 BDD scenario: `WebFetchBaseline` invoked without an Anthropic API key in env raises `LLMNotAvailable` with an actionable message.

## 3. Anthropic provider

- [ ] 3.1 `src/a2web/llm/providers/anthropic.py`: `AnthropicProvider` implementing the Provider protocol via the `anthropic` SDK.
- [ ] 3.2 Hardcoded pricing table for Haiku 4.5 + Sonnet 4.6 → `cost_usd` populated.
- [ ] 3.3 API key resolution: `settings.llm_api_key_env` (default `"ANTHROPIC_API_KEY"`) read via `os.environ` at construction time.
- [ ] 3.4 BDD scenario: provider returns a `ProviderResponse` with non-zero `cost_usd`, non-zero `prompt_tokens` and `completion_tokens`, non-zero `latency_ms` on a successful call.
- [ ] 3.5 BDD scenario: provider call fails with rate limit → returns a structured error response; does NOT raise (caller decides).

## 4. Extractor primitive

- [ ] 4.1 `Extractor(model, template, cache=None)`: dataclass with `extract(content, ask) -> ExtractionResult`.
- [ ] 4.2 ExtractionResult fields: `answer, model, template_name, prompt_tokens, completion_tokens, cost_usd, latency_ms, cache_hit: bool`.
- [ ] 4.3 Cache integration: compute `(content_hash, ask_hash, model_id)` key; on hit return `cache_hit=True, cost_usd=0.0, original_cost_usd=<stored>`.
- [ ] 4.4 BDD scenario: same `(content, ask, model)` invocation twice hits cache on second call; second call latency < 50 ms.
- [ ] 4.5 BDD scenario: same `content + ask` but different `model` invokes the provider both times (no cross-model sharing).

## 5. Judge primitive

- [ ] 5.1 `Judge(model)`: `score(task, criteria, answer) -> JudgeVerdict`.
- [ ] 5.2 JudgeVerdict shape: `scores: list[int], overall: int, reached: bool, reasoning: str, cost_usd: float, model: str`.
- [ ] 5.3 JSON parsing: try strict JSON; fall back to regex-extract-first-object; on failure raise `JudgeParseError` with the raw text.
- [ ] 5.4 BDD scenario: judge of a correct answer returns `overall >= 4`.
- [ ] 5.5 BDD scenario: judge of an "I cannot fetch" failure answer returns `reached=False` and `overall <= 1`.

## 6. Extraction cache

- [ ] 6.1 `src/a2web/llm/cache.py`: sqlite table `extraction_cache` created at module init (same db as HTTP cache).
- [ ] 6.2 TTL from `settings.extraction_cache_ttl_s` (default 900 — matching WebFetch).
- [ ] 6.3 Eviction: rows past `expires_at` deleted lazily on read; size cap configurable (default 50 MiB matching WebFetch `tg5`).
- [ ] 6.4 BDD scenario: cache hit returns cached answer + records `cache_hit=True`.
- [ ] 6.5 BDD scenario: cache row past TTL is treated as miss; refreshed on the new call.

## 7. Wire extraction into fetcher

- [ ] 7.1 `src/a2web/routers.py`: `fetch` tool gains `ask: Annotated[str | None, a2kit.Param(...)] = None`.
- [ ] 7.2 `src/a2web/fetcher.py`: when `ask` is non-None AND `state.llm_client` is available, after the extract phase, dispatch a new phase `_phase_extract_answer` that:
  - truncates `content_md` to `settings.extraction_max_chars` (default 100_000).
  - calls `Extractor.extract(content=..., ask=...)`.
  - populates `FetchResponse.extracted_answer` and `FetchResponse.extraction`.
- [ ] 7.3 When `ask` is set but `state.llm_client` is None (no `[llm]` extra OR no key): populate `operator_hints` with `code="llm_unavailable"` + actionable message. Don't fail the fetch.
- [ ] 7.4 BDD scenario: `fetch(url=..., ask="Who designed Rust?")` returns `extracted_answer` containing "Graydon Hoare".
- [ ] 7.5 BDD scenario: `fetch(url=...)` without `ask` produces `extracted_answer=None` and never invokes the llm module.
- [ ] 7.6 BDD scenario: `fetch(url=..., ask=...)` with no API key configured populates `operator_hints[code="llm_unavailable"]` and `extracted_answer=None`; main fetch succeeds.

## 8. Eval suite

- [ ] 8.1 `src/a2web/llm/eval/corpus.py`: `load_corpus(path) -> Corpus` (URLs, tasks, criteria).
- [ ] 8.2 `src/a2web/llm/eval/systems.py`: `EvalSystem` Protocol + `WebFetchBaseline` + `A2WebDetail` (full envelope, no ask) + `A2WebExtract` (ask= passed through).
- [ ] 8.3 `src/a2web/llm/eval/runner.py`: `EvalSuite.run()` orchestrates the matrix with bounded concurrency.
- [ ] 8.4 `src/a2web/llm/eval/report.py`: writes `results.tsv`, `leaderboard.md`, `cost.md`, `tokens.md`, `findings.md`, plus per-(slug,system) trace dir.
- [ ] 8.5 `src/a2web/llm/eval/__main__.py`: CLI entry. `uv run python -m a2web.llm.eval --corpus benchmarks/vs-webfetch/2026-05-11/corpus.yaml`.
- [ ] 8.6 Makefile targets: `make eval` (single model, current corpus), `make eval-full` (matrix), `make eval-baseline` (WebFetchBaseline only).
- [ ] 8.7 BDD scenario: `make eval` against the existing corpus produces a dated `eval/runs/<date>/results.tsv` with one row per (slug, system).
- [ ] 8.8 BDD scenario: eval run with one URL + one system + the Anthropic provider unavailable writes a results row with `error="llm_unavailable"`.

## 9. Migration

- [ ] 9.1 Move shared prompt logic from `benchmarks/vs-webfetch/2026-05-11/judge.py` into `src/a2web/llm/prompts.py`.
- [ ] 9.2 Update `benchmarks/vs-webfetch/2026-05-11/judge.py` to import from `a2web.llm` (replaces the inline `claude -p` subprocess).
- [ ] 9.3 Leave `benchmarks/vs-webfetch/2026-05-11/results.tsv` + `findings.md` + `summary.md` in place as the frozen v0.2 baseline.

## 10. Documentation

- [ ] 10.1 CLAUDE.md: add `llm/` module description under "Architecture", per the proposal blurb.
- [ ] 10.2 README.md: add a "Server-side extraction with `ask=`" section showing the WebFetch-parity use case.
- [ ] 10.3 CHANGELOG.md: v0.4 entry with the eval-suite headline and the `ask=` param.
- [ ] 10.4 BACKLOG.md: mark v0.4 items resolved; move OpenRouter / structured / MCP-resource items to v0.5 section.

## 11. Verification

- [ ] 11.1 `make check` clean.
- [ ] 11.2 `make eval` against the existing benchmark corpus produces a v0.4 leaderboard.
- [ ] 11.3 Compare v0.4 a2web-extract scores against WebFetchBaseline scores on the same corpus: target ≥ parity, expected slight win because a2web's content reach is better.
- [ ] 11.4 Confirm: bare `pip install a2web` (no `[llm]`) still imports cleanly and `fetch(url)` works.
- [ ] 11.5 Confirm: `pip install a2web[llm]` with `ANTHROPIC_API_KEY` set enables `fetch(url, ask=...)`.
