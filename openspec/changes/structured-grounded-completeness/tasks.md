## 1. thread the structured-grounded signal

- [ ] 1.1 In `_phase_gate_and_escalate` (`fetcher.py`), set `fc.structured_grounded = True` when — and only when — the `structured_answer` exemption is what flipped the gate verdict from `length_floor` to `ok` (compute the pre-exemption verdict, or have `evaluate` report that the promotion fired).
- [ ] 1.2 Carry `structured_grounded` onto `FetchResponse` as an internal, wire-invisible boolean (default `False`).

## 2. carve the obstacle rule

- [ ] 2.1 In `build_ask_response` (`fetcher_response.py`), gate the `obstacle in _INCOMPLETE_OBSTACLES` block: when `obstacle == "empty"` AND the answer is non-empty AND `fr.structured_grounded`, skip setting `retrieval_incomplete` and skip the critical hint — but still apply the `confidence = low` cap.
- [ ] 2.2 Confirm `blocked` (and `empty` on non-`structured_grounded` pages) keep today's behavior; confirm the `extraction_empty` hard-fail path is untouched.

## 3. tests

- [ ] 3.1 Unit (build_ask_response): `structured_grounded=True` + non-empty answer + `obstacle="empty"` → `retrieval_incomplete=False`, no critical hint, `confidence=low`.
- [ ] 3.2 Unit: `structured_grounded=True` + non-empty answer + `obstacle="blocked"` → still `retrieval_incomplete=True` (carve-out is empty-only).
- [ ] 3.3 Unit: `structured_grounded=False` + `obstacle="empty"` → unchanged (`retrieval_incomplete=True` + critical hint).
- [ ] 3.4 Orchestrator: the Veito-shape thin LocalBusiness fixture from `structured-data-answers` with a stub extractor returning a non-empty answer + `obstacle="empty"` → `status=ok`, `retrieval_incomplete` absent/false, no critical hint, `confidence=low`.
- [ ] 3.5 Orchestrator: same fixture, stub extractor returns an EMPTY answer → `status=failed` via `extraction_empty` (carve-out does not rescue an empty answer).

## 4. verify

- [ ] 4.1 `make check` green.
- [ ] 4.2 Live re-run of `veito.com/iletisim-EN.html`: answer present, `status` ok, `retrieval_incomplete` gone, `confidence` low.
