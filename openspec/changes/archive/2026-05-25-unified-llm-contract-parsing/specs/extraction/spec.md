# Spec delta — extraction

## ADDED Requirements

### Requirement: LLM boundary parsing uses an explicit wobble-tolerance policy

Every parser in the codebase that consumes LLM-returned JSON SHALL declare an explicit per-field wobble-tolerance policy drawn from a closed vocabulary of four values: `STRICT` (raise on missing/malformed), `DERIVE` (compute from already-parsed fields), `DEFAULT` (substitute a sentinel), `SKIP` (return `None` or an empty collection for the boundary or per-entry as documented). The policy SHALL live in a shared discipline module under `src/a2web/packages/llm_extract/` and SHALL be imported by every LLM-touching parser in the project.

The discipline module SHALL be domain-independent — it SHALL NOT import from `a2web.<domain>` (enforced by `tests/test_packages_independence.py`).

When any field's policy fires (i.e. the field is missing or malformed and a non-STRICT policy applies), the parser SHALL emit a single structured log event with key `llm_wobble` and the fields `boundary`, `field`, `policy_applied`, `model`, and a bounded `raw_excerpt` (≤ 200 chars). The legacy log keys (`routing_validation_failed`, `judge_failed`, `clarity_judge_failed`, `next_links_judge_failed`, and any silent-drop paths) SHALL be retired in favour of this single key.

The four migration sites SHALL adopt the discipline per the policy table documented in `design.md`. In particular:

- `Judge.score` SHALL treat `reached` as `DERIVE` (computed as `overall >= 3` when missing or null), retiring the current `JudgeParseError` raise for that specific field. Other judge fields (`scores`, `overall`) SHALL remain `STRICT`; `reasoning` SHALL be `DEFAULT` (empty string).
- `Extractor._split_answer_and_routing` SHALL keep its current behavior (`SKIP` the whole routing payload when `structural_form` or `shape` is missing), expressed via the shared discipline.
- `_project_routing` in `src/a2web/fetcher_response.py` SHALL keep its current behavior (`SKIP` the whole projected `RouterPayload` on closed-enum violation), expressed via the shared discipline; the log key SHALL change from `routing_validation_failed` to `llm_wobble`.
- `BenchJudge.score_clarity` and `BenchJudge.score_next_links` SHALL treat the numeric score as `STRICT` and `reasoning` as `DEFAULT` (empty string).

No public API SHALL change: `JudgeVerdict`, `ExtractionResult`, `RouterPayload`, `ClarityVerdict`, and `NextLinksVerdict` shapes are preserved.

#### Scenario: STRICT policy raises on missing required field

- **WHEN** `Judge.score` receives a model response missing `scores`
- **THEN** `JudgeParseError` is raised and no `llm_wobble` log event is emitted (the error path carries its own diagnostics)

#### Scenario: DERIVE policy recovers missing `reached` from `overall`

- **WHEN** `Judge.score` receives a model response containing `scores`, `overall=4`, `reasoning`, but no `reached` (the 2026-05-25 `wikipedia-rust / a2web_extract` trace)
- **THEN** the returned `JudgeVerdict.reached` is `True` (derived from `overall >= 3`), `JudgeVerdict.raw` carries `reached_derived: True`, no `JudgeParseError` is raised, and one `llm_wobble` log event fires with `boundary="judge"`, `field="reached"`, `policy_applied="derive"`

#### Scenario: DEFAULT policy substitutes sentinel for missing non-critical field

- **WHEN** `BenchJudge.score_clarity` receives a model response with `clarity=4` but no `reasoning`
- **THEN** the returned `ClarityVerdict.reasoning` is `""`, no `JudgeParseError` is raised, and one `llm_wobble` event fires with `boundary="bench_clarity"`, `field="reasoning"`, `policy_applied="default"`

#### Scenario: SKIP policy drops the whole boundary payload while sibling data survives

- **WHEN** `Extractor._split_answer_and_routing` receives a model response with a valid `answer` but missing `structural_form`
- **THEN** the returned tuple is `(answer, None)` — the `RouterPayload` is dropped but `answer` survives — and one `llm_wobble` event fires with `boundary="extractor_routing"`, `field="structural_form"`, `policy_applied="skip"`

#### Scenario: Closed-enum violation in `_project_routing` emits the unified log key

- **WHEN** `_project_routing` receives a package-side `RouterPayload` with `shape="something_not_in_literal_7"`
- **THEN** the function returns `None`, the answer-bearing caller is unaffected, and a single `llm_wobble` event fires with `boundary="fetcher_routing_mirror"`, `field="shape"`, `policy_applied="skip"` (replacing the legacy `routing_validation_failed` key)

#### Scenario: Discipline module respects packages-independence

- **WHEN** `tests/test_packages_independence.py` walks `src/a2web/packages/llm_extract/wobble.py`
- **THEN** zero imports from `a2web.<domain>` modules are detected
