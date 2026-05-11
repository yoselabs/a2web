# llm-eval (new)

## Purpose

The deterministic evaluation harness for comparing a2web variants against WebFetch (faithfully reproduced locally), across model and prompt-template axes. Produces dated, reproducible reports for regression detection and provider/prompt selection.

## ADDED Requirements

### Requirement: WebFetchBaseline faithfully reproduces Claude Code WebFetch

A class `WebFetchBaseline` SHALL be available in `src/a2web/llm/eval/systems.py` that reproduces Claude Code's WebFetch behavior end-to-end without invoking Claude Code itself. It SHALL:

1. Issue an HTTP GET via httpx with the same timeouts/limits as Claude Code (60 s timeout, 10 MiB body ceiling).
2. Convert HTML to markdown via `markdownify` (or an equivalent Turndown-compatible converter), applying a 1 MiB input cap and a 100,000-character output cap matching the `BD_` constant from research/123.
3. Submit the markdown + caller's `ask` string to the Anthropic provider with:
   - `model = "claude-haiku-4-5-20251001"` (per `LA()["haiku"]` in the binary)
   - `system = []` (per `iK([])`)
   - prompt = `WEBFETCH_DEFAULT_V1` (per `Rb9`)
   - `thinking_disabled = True` (per `thinkingConfig: {type: "disabled"}`)
   - no tools (per `tools: []`)
4. Return the model's first text block as the answer.

Known divergences from real WebFetch (documented in the module docstring):
- No `api.anthropic.com/api/web/domain_info` preflight (we always fetch).
- No cross-host redirect break (we follow within reason).
- No preapproved-host fast path (we always run Haiku).

#### Scenario: WebFetchBaseline returns the same answer pattern WebFetch would

- **WHEN** `WebFetchBaseline().fetch(url="https://en.wikipedia.org/wiki/Rust_(programming_language)", ask="Who designed Rust and when?")` is awaited
- **THEN** the answer contains "Graydon Hoare" and "2006"

### Requirement: EvalSuite runs the matrix and writes a dated report

`EvalSuite(corpus, systems, judge, concurrency=4, output_dir=...)` SHALL `await run() -> EvalReport`. The output directory SHALL contain:

- `corpus.frozen.yaml` — a copy of the corpus actually used
- `manifest.json` — `{ran_at, git_sha, systems: [...], judge_model, concurrency}`
- `results.tsv` — one row per `(slug, system)` with: judge_overall, reached, prompt_tokens, completion_tokens, total_tokens, cost_usd, cache_hit, error
- `leaderboard.md` — pivot of system × URL-class
- `cost.md` — total + per-system cost; cost-per-quality-point
- `tokens.md` — token totals + medians per system
- `findings.md` — auto-grouped insights (regressions vs prior run, system-class wins, cost outliers)
- `trace/<slug>/<system>/` — raw answer, judge JSON, the exact prompt sent

#### Scenario: a successful run produces the full output set

- **GIVEN** a corpus with 5 URLs and 2 systems
- **WHEN** `EvalSuite(...).run()` completes
- **THEN** `results.tsv` contains 10 rows
- **AND** `leaderboard.md`, `cost.md`, `tokens.md`, `findings.md` all exist and are non-empty
- **AND** `trace/<slug>/<system>/{answer.txt,judge.json,prompt.txt}` exists for every (slug, system) pair

### Requirement: EvalSuite gracefully records LLM-unavailable rows

When a system's `fetch(url, ask)` raises `LLMNotAvailable`, the eval runner SHALL record the row with `error="llm_unavailable"` and `judge_overall=null`. The run SHALL NOT abort on a single system's missing credentials.

#### Scenario: matrix with one unavailable system still completes

- **GIVEN** an `EvalSuite` with two systems, where one is configured against a provider whose API key is absent
- **WHEN** the suite runs
- **THEN** the available system's rows show real scores
- **AND** the unavailable system's rows show `error="llm_unavailable"` and `judge_overall=null`
- **AND** the leaderboard.md notes the unavailable system but does not omit it

### Requirement: Makefile exposes three eval entry points

`make eval`, `make eval-full`, `make eval-baseline` SHALL exist and run the corresponding eval shapes:

- `make eval` — single model (default Haiku 4.5), default corpus path, all configured systems.
- `make eval-full` — every configured model × every system × the default corpus.
- `make eval-baseline` — WebFetchBaseline only (drift-detection mode).

#### Scenario: make eval succeeds with a valid Anthropic key

- **GIVEN** `ANTHROPIC_API_KEY` is set and the `[llm]` extra is installed
- **WHEN** `make eval` is run from the repo root
- **THEN** the command exits 0
- **AND** a new `eval/runs/<today>/` directory is created with the full output set
