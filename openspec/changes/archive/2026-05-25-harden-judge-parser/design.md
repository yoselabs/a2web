# Design: Harden the judge parser against missing `reached`

## Decision 1: Derived semantics for `reached`

**Pick `reached = overall >= 3`** when the field is missing.

Two candidate definitions were on the table:

- `reached = (overall >= 3)` — a 1-5 score where 3 is the canonical "good enough" mid-point.
- `reached = all(s > 0 for s in scores)` — every criterion got a non-zero score.

Both are defensible, but `reached` is consumed by `src/a2web/llm_eval/report.py:289` (`reached = sum(1 for r in report.rows if r.system == system and r.judge_reached)`) and again as a per-system reach rate. The eval report is treating `reached` as the single-bit "answer was good enough" signal. The judge prompt's contract for `reached` is also overall-quality-flavoured ("did the answer reach the bar"), not per-criterion flavoured.

`overall >= 3` keeps the derived signal aligned with the operator-facing aggregation. The wikipedia-rust case (`overall: 4`) cleanly derives to `True`, which matches the human-eye reading of the verdict.

The threshold `3` is encoded as a module-level constant in the implementation (call it `_REACHED_DERIVED_THRESHOLD = 3`) so it can be tuned without scattering magic numbers, but it does not become a configuration knob — the judge contract is canonical.

## Decision 2: Tight scope — only `reached`, only missing-or-null

This proposal does not touch:

- Missing `scores` (the score vector is the raw signal — derivation here would be invention).
- Missing `reasoning` (the operator-readable string is the whole point of having a judge; if it's missing, the verdict is shaped wrong enough to throw).
- Type errors (`overall: "high"`, `scores: "5,3,5"` as a string). The current strict `int()` / `bool()` coercion stays — these are model bugs the harness should surface, not paper over.
- Missing `reached` *and* missing `overall` simultaneously — without `overall` there is nothing to derive from, so the parser still throws.

The broader "unify LLM contract parsing across judge + extractor + affordances" is a separate proposal. Calling it out here so reviewers don't push to expand scope: ship the narrow fix, watch it, then unify.

## Decision 3: Always-on with telemetry, no opt-in

An opt-in kwarg (`tolerate_missing_reached: bool = False` on `Judge.score`) was considered and rejected. The wobble is a model contract drift, not an operator preference — every consumer of `Judge` wants the same answer ("derive when safe, throw otherwise"). An opt-in would let the eval suite enable it and leave any future caller silently re-broken when the same model drift hits them.

Telemetry covers the operator-visibility concern:

- A `structlog` warning `judge_reached_missing` carrying `model`, `overall`, `derived_reached`. Mirrors the `routing_validation_failed` warning at `src/a2web/fetcher_response.py:73`.
- `JudgeVerdict.raw["reached_derived"] = True` so downstream code (eval report, future cache gates) can opt to treat derived verdicts differently if needed.

The bench / eval harness does not need a new column for this — `judge_error` stays `None` on derivation, and the raw JSON dump on disk already preserves the missing field for any post-hoc audit.

## Decision 4: Strict-field set stays a list, not a `dict[str, Any]` schema

The current parser's tight `try/except (KeyError, TypeError, ValueError)` over four `parsed[...]` accesses is fine. The change is local: split `reached` out of the strict block, then run the derivation. No new validation framework, no pydantic at the boundary, no closed-vocabulary type for "judge contract drift mode" — just an `if "reached" in parsed and parsed["reached"] is not None` branch.

This keeps the boundary cost low and avoids a `dict[str, Any]`-shaped degradation policy bag that would inevitably grow.

## Risk and rollback

- **Risk:** the model drifts further and starts omitting `overall` too. Mitigation: the parser still throws in that case; the bench still fails loudly.
- **Risk:** the derived threshold (`>= 3`) drifts from the report's aggregation if someone later changes the report. Mitigation: the constant is named (`_REACHED_DERIVED_THRESHOLD`), and a test pins the derivation to the documented threshold.
- **Rollback:** remove the derivation branch, restore the strict `bool(parsed["reached"])` line. No data migration — `JudgeVerdict.raw` is an unstructured bag already; the absence of `reached_derived` is the rollback state.
