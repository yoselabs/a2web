## 1. Corpus

- [ ] 1.1 Write `eval/corpus.yaml` with tricky-scenario entries: ≥1 Reddit comment thread, ≥1 HN comment/item page, ≥3 index/listing pages (Reddit listing, HN front, PyPI, gh-trending), plus a few clean/gated/SPA controls — each with `slug`, `url`, `class`, `task`, `needs`, `criteria` (criteria phrased against stable structural facts).
- [ ] 1.2 Mark listing entries in the corpus (`extra` field, e.g. `next_links_expected: true`) so the harness knows which cells get the `next_links_picked_correctly` axis.
- [ ] 1.3 Repoint `_DEFAULT_CORPUS` in `src/a2web/llm_eval/__main__.py` to `eval/corpus.yaml`.

## 2. Provider selection — no API key

- [ ] 2.1 Add a `_pick_provider()` helper to `__main__.py` that prefers `ClaudeCodeProvider`, falls back to `AnthropicProvider` on `LLMNotAvailable`, and honours an env override (`A2WEB_BENCH_PROVIDER`).
- [ ] 2.2 Replace the hardcoded `AnthropicProvider()` for both the judge and the `A2WebExtract` reader path; drop the "`ANTHROPIC_API_KEY` required" abort.
- [ ] 2.3 Test: `_pick_provider()` returns claude-code by default and honours the override.

## 3. Token-cost axis

- [ ] 3.1 Add an envelope per-field token breakdown helper (port `field_breakdown` from the retired runner, updated to the v0.14 envelope: `content_md`, `links`, `next_links`, `headings`, `diagnostics`, `debug`, `meta`, …).
- [ ] 3.2 Populate `SystemResult.metadata["envelope_tokens"]` (total + per-field) in `A2WebDetail` / `A2WebExtract`; for `WebFetchBaseline` record the returned-text token count.
- [ ] 3.3 Surface token cost as a first-class `EvalRow` field; add the test covering the breakdown.

## 4. Data-contract conformance axis (deterministic)

- [ ] 4.1 Add `check_envelope_contract(envelope: dict) -> ContractResult` in `llm_eval/` — asserts deviation-only `tier`/`url`/`status`, `debug` only under `debug=True`, `next_links` shape; returns pass + list of violations.
- [ ] 4.2 Test (write first): conformant envelope passes; a leaked `tier="raw"` / `status="ok"` / un-gated `debug` each fails with the offending field named.
- [ ] 4.3 Run the a2web systems once with `debug=False` and once with `debug=True`; record the contract result on the `EvalRow`.

## 5. Output-clarity judge axis

- [ ] 5.1 Extend the judge prompt in `src/a2web/packages/llm_extract/prompts.py` (or a benchmark-local judge template) with an output-clarity rubric: can a downstream agent act on this output directly.
- [ ] 5.2 Test: judge returns a clarity score in range for a clean answer and a low score for a noisy one.

## 6. next_links_picked_correctly axis

- [ ] 6.1 Add the `next_links_picked_correctly` judge axis; apply it only to cells whose corpus entry is marked listing (task 1.2).
- [ ] 6.2 Test: a listing entry is scored on the axis; a permalink entry is not.

## 7. Report + EvalRow/EvalReport wiring

- [ ] 7.1 Extend `EvalRow` / `EvalReport` with the new axis fields; thread them through `runner._run_one`.
- [ ] 7.2 Extend `report.py` (`write_all`, `stats_dict`) to render the four axes per system and a vs-WebFetch summary table.
- [ ] 7.3 Test: a full in-process `EvalSuite` run over a 2-entry stub corpus produces a report carrying all four axes.

## 8. Command + retire the stale harness

- [ ] 8.1 Add a `make bench` target (or document `python -m a2web.llm_eval`); keep `make eval` working.
- [ ] 8.2 Delete the stale `benchmarks/vs-webfetch/2026-05-11/` runnable scripts (`runner.py`, `judge.py`, `aggregate.py`, `multi_model.py`, `phase4_ask.py`, `reliability_runner.py`); keep the `findings_*.md` as history.
- [ ] 8.3 Update `CHANGELOG.md` and the README eval/benchmark section.

## 9. Tests live with the new capability

- [ ] 9.1 Place the new tests under `tests/capabilities/output_benchmark/` (per the test-layout capability), with `__init__.py`.

## 10. Run the benchmark + capture findings

- [ ] 10.1 Run `make bench` against `eval/corpus.yaml` (claude-code provider, live network).
- [ ] 10.2 Write a findings summary (a2web vs WebFetch across the four axes; where a2web wins/loses; any contract failures) committed alongside the dated run report.

## 11. Verify the gate

- [ ] 11.1 `make check` passes — lint, `ty`, full suite, coverage ≥ 85%.
