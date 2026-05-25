# Extraction spec delta

## ADDED Requirements

### Requirement: Judge parser tolerates a missing `reached` field by deriving it from `overall`

`Judge._parse_verdict_json` SHALL accept judge responses that omit (or set to `null`) the `reached` field when `scores`, `overall`, and `reasoning` are all present and well-typed. In that case the parser SHALL derive `reached = (overall >= 3)`, MUST emit a `structlog` warning named `judge_reached_missing` carrying the model name, the parsed `overall`, and the derived value, and MUST populate `JudgeVerdict.raw["reached_derived"] = True`. The verdict SHALL otherwise round-trip identically to a verdict where the model returned `reached` explicitly.

`Judge` SHALL continue to raise `JudgeParseError` when any of `scores`, `overall`, or `reasoning` is missing or malformed, and when `reached` is present but not coercible to `bool`. The derivation path SHALL only apply when `reached` is absent from the parsed JSON or explicitly `null`.

Eval consumers (`src/a2web/llm_eval/runner.py`) SHALL treat a derived verdict as a successful judgment: `row.judge_error` SHALL remain `None`, `row.judge_reached` SHALL carry the derived `bool`, and the row SHALL count toward the system's reach-rate aggregation in `src/a2web/llm_eval/report.py`.

#### Scenario: Model omits `reached` on an otherwise well-formed verdict

- **WHEN** the judge LLM returns `{"scores":[5,3,5], "overall":4, "reasoning":"..."}` with no `reached` key
- **THEN** `Judge.score` returns a `JudgeVerdict` with `overall=4`, `scores=[5,3,5]`, `reached=True`, `raw["reached_derived"]=True`, and a `judge_reached_missing` warning is emitted

#### Scenario: Model returns `reached: null` on an otherwise well-formed verdict

- **WHEN** the judge LLM returns `{"scores":[1,0], "overall":1, "reached": null, "reasoning":"miss"}`
- **THEN** `Judge.score` returns a `JudgeVerdict` with `reached=False` (derived from `overall=1 < 3`), `raw["reached_derived"]=True`, and a `judge_reached_missing` warning is emitted

#### Scenario: Fully-formed verdict still round-trips unchanged

- **WHEN** the judge LLM returns `{"scores":[5,5], "overall":5, "reached": true, "reasoning":"ok"}`
- **THEN** `Judge.score` returns a `JudgeVerdict` with `reached=True`, `raw["reached_derived"]` is absent (or falsy), and no `judge_reached_missing` warning is emitted

#### Scenario: Missing `overall` still raises `JudgeParseError`

- **WHEN** the judge LLM returns `{"scores":[5], "reasoning":"x"}` with no `overall` and no `reached`
- **THEN** `Judge.score` raises `JudgeParseError` carrying the raw text — derivation requires a parsed `overall`

#### Scenario: Missing `reasoning` still raises `JudgeParseError`

- **WHEN** the judge LLM returns `{"scores":[5], "overall":5}` with no `reached` and no `reasoning`
- **THEN** `Judge.score` raises `JudgeParseError` — the derivation branch only rescues `reached`, not `reasoning`

#### Scenario: Eval row records a derived verdict as a successful judgment

- **WHEN** a benchmark cell receives a verdict whose `reached` was derived
- **THEN** the resulting row carries `judge_error=None`, `judge_reached` set to the derived bool, and `judge_overall` populated; the run report counts the row toward the system's reach rate
