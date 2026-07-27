# Tasks

## 1. Discovery walk + fidelity check

- [ ] 1.1 Add `tests/architecture/test_llm_double_fidelity.py` with a discovery walk over `tests/` finding classes that structurally quack like an LLM provider or extractor double (an `async def complete(...)` or `async def extract(...)`).
- [ ] 1.2 Assert each discovered double is contract-faithful (handed `EXTRACT_ROUTER_V1`, returns a recoverable envelope) OR declares `DOUBLES_ARM` naming the degraded arm it exists to exercise.
- [ ] 1.3 Add the non-vacuity floor (`minimum=`) per `_walk.walked_files` discipline; assert the walk fails when it finds zero candidates.
- [ ] 1.4 Add the bidirectional sensitivity case: a double that returns an envelope for a NON-routing contract must FAIL the check.
- [ ] 1.5 Delete `tests/capabilities/ask_response/test_stub_provider_fidelity.py` — subsumed, not retained beside the general mechanism.
- [ ] 1.6 Annotate existing intentional degraded doubles with `DOUBLES_ARM`.

## 2. Replay harness

- [ ] 2.1 `tests/eval_replay/harness.py`: populate the routing payload from the cassette instead of leaving it `None`.
- [ ] 2.2 Raise a named, actionable error (case + re-capture command) when a cassette cannot express routing. No `None` fallback.
- [ ] 2.3 Distinguish "recorded as lost" from "format cannot say" so a deliberately-degraded case stays expressible and does not trip the loud failure.
- [ ] 2.4 Add a test that a legacy-format cassette fails loud rather than replaying degraded.

## 3. Cassette format

- [ ] 3.1 `eval/_capture/capture.py`: record the routing payload alongside the existing post-parse fields.
- [ ] 3.2 Version or mark the format so the replay side can tell new from legacy without guessing.
- [ ] 3.3 Update `eval/_capture/README.md` for the new field and the re-capture requirement.

## 4. Re-capture the corpus

- [ ] 4.1 Re-capture the 5 cases holding LLM responses (live network + LLM; `A2WEB_BENCH_PROVIDER=claude-code-sdk`, ADR-0016 subscription only).
- [ ] 4.2 Verify each replays through the `recovered` branch.
- [ ] 4.3 For any case that cannot be re-captured (dead URL / changed page), re-point or retire it DELIBERATELY and record which and why — never keep a stale cassette.

## 5. Gate

- [ ] 5.1 `make check` green.
- [ ] 5.2 `make arch` green.
- [ ] 5.3 Confirm zero production-code changes in the diff. If any turned out to be required, STOP and report rather than folding it in.
- [ ] 5.4 Confirm no wire goldens moved — this change must be wire-neutral.
