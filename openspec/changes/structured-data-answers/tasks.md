## 1. json-extract package: strong types + predicate

- [x] 1.1 Widen `_PREFERRED_LD_TYPES` in `src/a2web/packages/json_in_script.py` to add `LocalBusiness`, `Organization`, `ContactPoint`, `Event`, `Recipe`.
- [x] 1.2 Confirm `_ld_json_strong` / `_microdata_strong` handle the new types (single-string and list `@type`, generic type-set match), keeping the `≥3 populated fields beyond @type` threshold. (Both are type-set driven — new types work without further change.)
- [x] 1.3 Add public `is_answer_bearing(payload: JsonPayload) -> bool` returning `True` only for strong `ld_json` / strong `microdata`; `False` for all other sources and weak payloads.
- [x] 1.4 Export `is_answer_bearing` from the package `__all__`. (Frozen-boundary arch test covers only frozen dataclasses + `packages/*/__init__.py`; `json_in_script.py` is a flat module — no test change needed.)

## 2. extraction ladder: tag candidates answer-bearing + render entity schemas

- [x] 2.1 Add typed `answer_bearing: bool = False` field to `ContentCandidate` (frozen slotted dataclass — no dict bag).
- [x] 2.2 In `_escalate_via_json` (`fetcher.py`), set `answer_bearing=is_answer_bearing(payload)` on each `json_synth` candidate; keep trafilatura / `record_synth` at `False`.
- [x] 2.3 Widen the single-entity JSON-LD renderer dispatch in `domain.py::_ld_json_to_markdown` to include `LocalBusiness`, `Organization`, `ContactPoint`, `Event` (they fell through to an empty render). Discovered during 5.4 — the default-keep field logic already handles them once dispatched.

## 3. quality-gate exemption (the load-bearing fix)

- [x] 3.1 Add a `structured_answer: bool = False` parameter to the `evaluate(...)` seam in `fetcher.py`; mirror the `is_json` block, scoped to bare `length_floor` (`subsystem is None`) so a `js_required` / `thin_browser` shell keeps escalating.
- [x] 3.2 In `_phase_gate_and_escalate`, compute `structured_answer = any(c.answer_bearing for c in fc.content_candidates)` and pass it into `evaluate(...)`.

## 4. display pick

- [x] 4.1 In `_pick_display_candidate`, when the prose pick is below `LENGTH_FLOOR` and an `answer_bearing` structured candidate exists, return the structured candidate for `content_md`. Above-floor prose behavior unchanged.

## 5. tests

- [x] 5.1 Unit: `is_answer_bearing` — strong Product/LocalBusiness/microdata → True; weak 2-field Organization / opengraph / next_data → False.
- [x] 5.2 Unit: `rank_payloads` — strong LocalBusiness ld_json ranks bucket 0 ahead of opengraph; weak Organization ranks behind next_data.
- [x] 5.3 Gate: bare `length_floor` + `structured_answer` → promoted to `ok`, subsystem `None`; without → stays `length_floor`; `js_required` shell + `structured_answer` → stays `length_floor`/`js_required` (browser escalation intact).
- [x] 5.4 Orchestrator (`fetcher.fetch`): thin Veito-shape `LocalBusiness` JSON-LD (phone + email) with `ask=` → `status=ok`, extraction runs, structured rows reach the LLM.
- [x] 5.5 Display/`fetch_raw`: same fixture, no LLM → `content_md` carries phone + email; above-floor-prose fixture → prose still wins display.

## 6. verify

- [x] 6.1 `make check` green (lint + ty + tests, coverage ≥85%). → 1125 passed, coverage 89.9%, arch validated.
- [ ] 6.2 Add a contact-page case to `eval/corpus.yaml`; run `make bench` and record findings in `eval/findings_<date>.md` (structured-page class moved output quality). [live-network + LLM quota — deferred to a bench pass]
- [x] 6.3 Live smoke on real `https://www.veito.com/iletisim-EN.html`: returns `444 3 061` + `destek@veito.com` with status ok (was `failed/null`). CAVEAT discovered → see task 7.

## 7. follow-up discovered during live smoke (moved to its own change)

- [x] 7.1 A promoted thin page returns a correct structured answer AND `obstacle: "empty"` → `retrieval_incomplete: true` + a critical hint, a self-contradiction. **Scoped out into its own OpenSpec change `structured-grounded-completeness` — not implemented here** (touches ADR-0009 extractor-safety semantics; deserves separate scoping).
