# Harden the judge parser against missing `reached`

## Why

The judge boundary already mirrors the router-shape boundary's intent — accept structured LLM JSON, validate it, surface a wobble cleanly when the model drifts. The router boundary follows that discipline: `_project_routing` (`src/a2web/fetcher_response.py:45`) catches closed-enum violations on `RouterPayload.model_validate`, logs a warning, returns `None`, and the rest of the response survives.

The judge boundary does not. The 2026-05-25 bench run (`eval/runs/2026-05-25_183411/trace/wikipedia-rust/a2web_extract/`) returned a fully-formed verdict — `{"scores":[5,3,5], "overall":4, "reasoning": "..."}` — but the model omitted the `reached` field. The parser at `src/a2web/packages/llm_extract/judge.py:109` raised `JudgeParseError`. A 4.0-overall judgment was discarded for a missing optional-feeling field; the bench reported `judge_failed`.

`reached` is a derived signal — it expresses "did the answer hit the threshold." With `scores` and `overall` already present, the parser can derive it instead of throwing. This proposal aligns the judge boundary with the router boundary's graceful-degradation discipline for the `reached`-missing case only.

## What Changes

- The judge parser SHALL derive `reached` from `overall` (specifically `overall >= 3`, matching how `report.py` aggregates the reach rate) when the field is missing or `None` in the model's JSON. Other required fields (`scores`, `overall`, `reasoning`) remain required.
- The parser SHALL log a structured warning (`judge_reached_missing`) on the derivation path, carrying the derived value and the model name.
- The verdict SHALL surface the wobble: `JudgeVerdict.raw` SHALL carry `reached_derived: True` when the parser had to derive the field. The eval `runner.py` already populates `row.judge_error` from `JudgeParseError`; on a derivation, no `judge_error` is set — the row counts as a successful judgment.
- Behaviour is always-on (no opt-in kwarg). The wobble surfaces via the warning log and the `raw` field; operators see the derivation without having to enable a mode.
- No change to the verdict wire / dataclass shape beyond an additional key inside the existing `raw: dict[str, Any]`.

**Out of scope.** Broader LLM JSON tolerance — missing `scores`, missing `reasoning`, malformed types — is intentionally not covered here. Those failures still raise `JudgeParseError`. A separate proposal (`unified-llm-contract-parsing`) can take that pattern across `judge.py` + `extractor.py` + the affordances parser once we've shipped this narrow fix and watched it in production.

## Impact

- **Affected specs:** `extraction` — adds one requirement covering judge tolerance, sitting next to the existing "Router-shape parsing tolerates malformed JSON" requirement (`openspec/specs/extraction/spec.md:191`). The judge lives in the same `packages/llm_extract` surface, so the spec capability matches.
- **Affected code (implementation, not part of this proposal):**
  - `src/a2web/packages/llm_extract/judge.py` — parser branch + warning log + raw-key.
  - `tests/packages/llm_extract/test_llm_judge.py` — replace the "missing field" negative test for `reached` with a derivation test; add regression for the fully-formed path.
- **No public API change.** `JudgeVerdict` shape unchanged. `JudgeParseError` still raised for other missing/malformed fields. Eval `runner.py` keeps the `judge_error` semantics for everything except the derived-`reached` path.
