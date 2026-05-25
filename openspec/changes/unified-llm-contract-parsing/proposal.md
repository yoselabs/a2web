# Unified LLM contract-parsing discipline

## Why

LLM output is fundamentally lossy. Across the codebase today, four boundaries parse model-returned JSON, each with its own ad-hoc discipline:

1. **`src/a2web/packages/llm_extract/judge.py`** — the product judge. Raises `JudgeParseError` on any missing required field. Callers in `llm_eval/runner.py` translate that into a `judge_failed` cell outcome (the whole judge axis for the cell is lost).
2. **`src/a2web/packages/llm_extract/extractor.py`** — the extraction call (`_split_answer_and_next_links`, `_split_answer_and_routing`). Already best-effort: malformed JSON yields `(text, [])` or `(text, None)`, but the policy is open-coded per branch with no shared logging vocabulary.
3. **`src/a2web/fetcher_response.py::_project_routing`** — projects the package-side `RouterPayload` boundary into the pydantic mirror. Catches closed-enum violations, emits a structured `routing_validation_failed` warning, returns `None`. The exemplar pattern.
4. **`src/a2web/llm_eval/bench_judge.py`** — bench-only clarity + next_links sub-judges. Each raises `JudgeParseError`; callers swallow it with a `clarity_judge_failed` / `next_links_judge_failed` warning and drop the axis.

The 2026-05-25 bench run (`eval/runs/2026-05-25_183411/trace/wikipedia-rust/a2web_extract/`) failed a cell because the judge LLM returned a fully-formed verdict (`scores=[5,3,5], overall=4, reasoning="..."`) but omitted `reached`. The product judge raised `JudgeParseError`; `runner.py` recorded `judge_failed`. A 4.0-overall judgment that could have been derived from `overall` became `judge_failed` noise.

The structural cause is the absence of a shared discipline. Each site invents its own wobble vocabulary (raise vs. silent-drop vs. return-None), each chooses its own log key (`routing_validation_failed`, `judge_failed`, `clarity_judge_failed`), and no per-site policy is recorded in the spec. The sibling proposal `harden-judge-parser` lands the single most-painful case (judge `reached` derivation) but leaves the broader inconsistency in place.

## What Changes

- Introduce a `WobbleTolerance` discipline owned by `src/a2web/packages/llm_extract/` (alongside the existing `Judge` / `Extractor` / `RouterPayload` surface). The discipline names four explicit policies per missing/malformed field: `STRICT` (raise), `DERIVE` (compute from other fields), `DEFAULT` (use sentinel), `SKIP` (return `None` for the whole boundary).
- Migrate the four known sites to the discipline. Each site declares its **per-field policy table** in code; behavior is no longer ad-hoc. The four sites and their policies are catalogued in `design.md`.
- Every wobble emits a structured `llm_wobble` log event carrying `boundary` (e.g. `"judge"`), `field`, `policy_applied`, `raw_excerpt`. Sinks can fan it into OTel / bench reports without re-discovering log keys.
- Absorb the `harden-judge-parser` proposal: this proposal's judge-policy table includes the `reached` derivation. `harden-judge-parser` can ship independently (single-file scope, no shared helper); this proposal lands on top, swapping the open-coded derivation for the shared discipline. If `harden-judge-parser` has not landed by the time this one starts, this proposal supersedes it.
- No public API change. Wire-shape unchanged. The discipline is internal mechanics.

**Out of scope.** Provider-level retries on `JudgeParseError` (the discipline is parsing, not transport). Replacing pydantic with a different validation library. Cross-language schema sharing.

## Impact

- **Affected specs:**
  - `extraction` — adds one requirement, "LLM boundary parsing uses an explicit wobble-tolerance policy". Sits beside the existing "Router-shape parsing tolerates malformed JSON and omitted optional fields" requirement at `openspec/specs/extraction/spec.md:191`.
  - No new capability — `extraction` already owns `Extractor`, `Judge`, and the router boundary. Promoting a new `llm-contract-parsing` capability would split the same surface across two specs; the discipline is best read alongside the parser it governs.
  - `output-benchmark` capability is **not** modified — `bench_judge.py` is a consumer of the shared discipline, not the discipline owner. Its behavior change (clarity / next_links axes no longer drop on `reasoning` wobble) is observable but the spec language stays in `extraction`.
- **Affected code (implementation, not part of this proposal):**
  - New: `src/a2web/packages/llm_extract/wobble.py` — discipline module (enum + dataclass + `apply_policy` helper + `emit_wobble_log` structured log helper).
  - `src/a2web/packages/llm_extract/judge.py` — policy table swap; `reached` becomes `DERIVE` (matches `harden-judge-parser`).
  - `src/a2web/packages/llm_extract/extractor.py` — `_split_answer_and_routing` + `_split_answer_and_next_links` swap to the shared policy/log helper; behavior identical, vocabulary unified.
  - `src/a2web/fetcher_response.py::_project_routing` — already conforms in spirit; swap log key + raw-excerpt format to the shared `llm_wobble` schema.
  - `src/a2web/llm_eval/bench_judge.py` — clarity + next_links parsers use the discipline. `reasoning` becomes `DEFAULT` (empty string) when missing; `score` stays `STRICT` (the axis is meaningless without it).
  - `tests/packages/llm_extract/test_wobble.py` — new; matrix over the four policies.
  - `tests/test_packages_independence.py` — sanity: `wobble.py` has zero `a2web.<domain>` imports.
  - One cross-cutting test (`tests/test_llm_boundary_audit.py`) asserts every LLM-touching parser in `src/a2web/` declares a policy table or calls the shared helper.
- **No public API change.** `JudgeVerdict` / `ExtractionResult` / `RouterPayload` / `ClarityVerdict` / `NextLinksVerdict` shapes unchanged. `JudgeParseError` still raised for `STRICT`-policy fields.
- **One operator-visible behavior change.** The product judge no longer `judge_failed`s on `reached`-missing — it derives from `overall`. Matches the `harden-judge-parser` regression fix.
