## Why

a2web has no re-runnable benchmark. The one that existed — `benchmarks/vs-webfetch/2026-05-11/` — is a pile of dated ad-hoc scripts that predate the v0.11 (`fit_md` removal) and v0.14 (deviation-only `tier`/`url`/`status`, wire-only `debug` object) envelopes and the `ask`/`fetch_raw` split. Its `runner.py` calls a CLI subcommand that no longer exists and reads fields that were deleted; it cannot run. Every envelope change silently rots it because it lives outside the package as throwaway scripts. We keep needing to answer "did this change make a2web's output better or worse for an agent?" and have no maintained instrument to answer it. We need a benchmark that is typed, covered, package-resident, and survives envelope changes — one we re-run, not rewrite.

## What Changes

- Extend the existing maintained harness at `src/a2web/llm_eval/` into the canonical benchmark, rather than adding more standalone `benchmarks/` scripts. It already has the matrix runner (`EvalSuite`), the typed `Judge`, and three systems (`WebFetchBaseline`, `A2WebDetail`, `A2WebExtract`).
- Measure four axes per (URL, system) cell:
  1. **Answer quality** — judge score against per-question criteria (exists today).
  2. **Token cost** — tokens of the a2web response envelope itself (per-field breakdown), the payload an agent pays for. New; today only LLM-call tokens are counted.
  3. **Output clarity** — a new judge axis: how cleanly an agent can act on the output.
  4. **Data-contract conformance** — a new deterministic (non-LLM) check that the a2web envelope obeys its field-presence rules (deviation-only `tier`/`url`/`status`, `debug` only under `debug=True`, `next_links` shape).
- Add a `next_links_picked_correctly` judge axis applied to listing-style URLs (PyPI, gh-trending, Reddit/HN listings).
- Ship a tricky-scenario corpus emphasizing the cases that break naive fetchers: Reddit comment threads, Hacker News comment/item pages, and index/listing pages — alongside the existing clean/gated/SPA classes.
- Keep the head-to-head **vs-WebFetch** comparison. `WebFetchBaseline` is already a faithful in-process reproduction of Claude Code's WebFetch, so the comparison runs fully automated — no interactive phase.
- Judge runs on `claude-sonnet` via the `claude-code` provider (OAuth subscription) — no `ANTHROPIC_API_KEY` required.
- A single command (`make bench` / `python -m a2web.llm_eval`) runs the suite and writes a dated report. Retire the stale `benchmarks/vs-webfetch/2026-05-11/` scripts; keep its `findings_*.md` only as history.

## Capabilities

### New Capabilities
- `output-benchmark`: the re-runnable benchmark contract — the four measurement axes (quality, token cost, clarity, data-contract conformance), the `next_links_picked_correctly` axis, the corpus format and required tricky-scenario coverage, the vs-WebFetch baseline requirement, and the rule that the benchmark is package-resident and covered so it cannot silently rot.

### Modified Capabilities
<!-- None. The benchmark observes the envelope; it does not change any product capability's requirements. -->

## Impact

- `src/a2web/llm_eval/` — new measurement axes wired through `CorpusEntry`, `EvalRow`, `EvalReport`, `runner.py`, `report.py`; new corpus YAML; the `Judge` prompt gains the clarity + next_links axes.
- `Makefile` — a `bench` target (or extend `eval`).
- Supersedes tasks **10.1 / 10.2 / 10.3** of `link-discovery-next-candidates` — those assumed re-running the now-dead harness; the `next_links` benchmark axis is owned here instead. `link-discovery-next-candidates` can archive at its current state.
- No `src/a2web/<product>` behavior change, no dependency change, no wire/API change.
