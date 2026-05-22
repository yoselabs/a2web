## 1. Orchestrator change

- [x] 1.1 Add `handler_not_found: bool = False` to `FetchContext` in `src/a2web/fetcher.py`, with a short comment explaining it captures a site handler's authoritative `not_found`.
- [x] 1.2 In `_phase_tier_loop`, set `fc.handler_not_found = True` when the `site_handler` tier returns `Verdict.not_found` (after the `no_match`/`skipped` silent-skip guard, before the loop continues).
- [x] 1.3 Add a named reconciliation phase `_phase_reconcile_verdict(fc)` — if `fc.final_verdict != Verdict.ok` and `fc.handler_not_found`, set `fc.final_verdict = Verdict.not_found`. Call it in `_run_pipeline` after `_phase_gate_and_escalate` and before `build_response`.

## 2. Tests

- [x] 2.1 Write a test in `tests/capabilities/tier_pipeline/`: stub `site_handler` registry entry returns `Verdict.not_found`, stub `raw` tier returns HTTP 200 with a sub-length-floor body → drive `fetcher.fetch` → assert the final `FetchResponse` verdict is `not_found` (not `length_floor`) and `status` is `failed`.
- [x] 2.2 Write a test: stub `site_handler` returns `Verdict.not_found`, stub `raw` returns gate-passing content → assert `status` is `ok` (the precedence rule does not clobber a recovery).
- [x] 2.3 Write a test: no handler `not_found` in the fetch, fetch fails with `length_floor` → assert the verdict stays `length_floor` (precedence rule does not fire).

## 3. Verify

- [x] 3.1 `make check` passes — lint, `ty`, full suite, coverage ≥ 85%.
