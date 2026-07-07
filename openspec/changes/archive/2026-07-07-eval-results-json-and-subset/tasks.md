## 1. results.json + cost/token summary

- [x] 1.1 In `report.py`, add `_write_results_json` — a `{summary, rows}` file: rows = per-cell objects (scores + `fetch_cost_usd`, fetch prompt/completion tokens, `judge_cost_usd`); summary = `total_cost_usd` + total prompt/completion tokens, overall and per-system
- [x] 1.2 Wire it into `write_all`; keep `results.tsv` / `manifest.json` / `cost.md` unchanged
- [x] 1.3 Test (stub rows): `results.json` has a `rows` array matching the row count and a `summary` with the correct cost/token totals

## 2. --only class subset filter

- [x] 2.1 Add `--only <class>` to the argparse in `__main__.py`
- [x] 2.2 Filter the loaded corpus by case `class` right after `load_corpus`; absent → full corpus
- [x] 2.3 Empty match → print "0 cases match class X (known: …)" and exit non-zero
- [x] 2.4 Test: `--only listing` keeps only listing cases; unknown class exits non-zero with the message

## 3. Selection-question corpus case

- [x] 3.1 Add one `listing`-class case to `eval/corpus.yaml` with a "which is best?" selection task over a stable in-reach listing
- [x] 3.2 Expectations reward presenting options/criteria; do NOT require a single unqualified "best" (criterion-disclosed lead acceptable)
- [x] 3.3 Test: corpus loads with the selection case present (a case whose task is a selection question exists)

## 4. Verification

- [x] 4.1 `make check` green (stub-driven; no live LLM calls); coverage ≥85%
- [x] 4.2 Update CHANGELOG.md
- [ ] 4.3 (Deferred, user-gated) a crucial `--only listing --mode detail` bench run on the subscription — NOT run here; the user decides when to spend the budget
