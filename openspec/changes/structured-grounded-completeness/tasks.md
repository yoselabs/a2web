## 1. thread the structured-grounded signal

- [x] 1.1 In `_phase_gate_and_escalate` (`fetcher.py`), set `fc.structured_grounded = True` when — and only when — the `structured_answer` exemption flipped the verdict from `length_floor` to `ok`. Done via `_GateResult.promoted_structured` (evaluate reports the promotion fired).
- [x] 1.2 Carry `structured_grounded` onto `FetchResponse` as an internal, wire-invisible boolean (`Field(default=False, exclude=True)`; set in `build_response` from `fc`).

## 2. carve the obstacle rule

- [x] 2.1 In `build_ask_response` (`fetcher_response.py`), gate the `obstacle in _INCOMPLETE_OBSTACLES` block: `obstacle == "empty"` AND non-empty answer AND `fr.structured_grounded` → skip `retrieval_incomplete` + the critical hint, keep the `confidence = low` cap (the cap fires independently since `empty ∈ _CONFIDENCE_CAPPING_OBSTACLES`).
- [x] 2.2 Confirmed `blocked` and `empty` on non-grounded pages keep today's behavior. **Extended** the `extraction_empty` hard-fail: its `len(content_md) > 500` threshold assumed thin pages already failed at the length floor — now `or fc.structured_grounded`, so a promoted thin page with an empty extraction still hard-fails (ADR-0009). Found via test 3.5.

## 3. tests

- [x] 3.1 Unit (build_ask_response): `structured_grounded=True` + non-empty answer + `obstacle="empty"` → `retrieval_incomplete=False`, no critical hint, `confidence=low`.
- [x] 3.2 Unit: `structured_grounded=True` + `obstacle="blocked"` → still `retrieval_incomplete=True` (carve-out is empty-only).
- [x] 3.3 Unit: `structured_grounded=False` + `obstacle="empty"` → unchanged; plus an empty-answer-still-flagged unit case.
- [x] 3.4 Orchestrator: Veito-shape thin LocalBusiness fixture, stub extractor returns a router envelope (non-empty answer + `obstacle="empty"`) → `status=ok`, `structured_grounded=True`, `retrieval_incomplete` false, no critical hint, `confidence=low`.
- [x] 3.5 Orchestrator: same fixture, stub extractor returns an EMPTY extraction → `status=failed` + `retrieval_incomplete` (extraction_empty guard, extended per 2.2).

## 4. verify

- [x] 4.1 `make check` green (1131 passed, 89.9% cov; contract re-blessed for the new `structured_grounded` field on `fetch_raw`).
- [ ] 4.2 Live re-run of `veito.com/iletisim-EN.html`: answer present, `status` ok, `retrieval_incomplete` gone, `confidence` low. [after install-global in the release step]
