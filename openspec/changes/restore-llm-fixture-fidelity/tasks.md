# Tasks

## 1. Discovery walk + fidelity check

- [x] 1.1 Add `tests/architecture/test_llm_double_fidelity.py` with a discovery walk over `tests/` finding classes that structurally quack like an LLM provider or extractor double (an `async def complete(...)` or `async def extract(...)`).
- [x] 1.2 Assert each discovered double is contract-faithful (handed `EXTRACT_ROUTER_V1`, returns a recoverable envelope) OR declares `DOUBLES_ARM` naming the degraded arm it exists to exercise.
- [x] 1.3 Add the non-vacuity floor (`minimum=`) per `_walk.walked_files` discipline; assert the walk fails when it finds zero candidates.
- [x] 1.4 Add the bidirectional sensitivity case: a double that returns an envelope for a NON-routing contract must FAIL the check.
- [x] 1.5 Delete `tests/capabilities/ask_response/test_stub_provider_fidelity.py` — subsumed, not retained beside the general mechanism.
- [x] 1.6 Annotate existing intentional degraded doubles with `DOUBLES_ARM`.

## 2. Replay harness

- [x] 2.1 `tests/eval_replay/harness.py`: populate the routing payload from the cassette instead of leaving it `None`.
- [x] 2.2 Raise a named, actionable error (case + re-capture command) when a cassette cannot express routing. No `None` fallback.
- [x] 2.3 Distinguish "recorded as lost" from "format cannot say" so a deliberately-degraded case stays expressible and does not trip the loud failure.
- [x] 2.4 Add a test that a legacy-format cassette fails loud rather than replaying degraded.

## 3. Cassette format

- [x] 3.1 `eval/_capture/capture.py`: record the routing payload alongside the existing post-parse fields.
- [x] 3.2 Version or mark the format so the replay side can tell new from legacy without guessing.
- [x] 3.3 Update `eval/_capture/README.md` for the new field and the re-capture requirement.

## 4. Re-capture the corpus

- [x] 4.1 Re-capture the 5 cases holding LLM responses (live network + LLM; `A2WEB_BENCH_PROVIDER=claude-code-sdk`, ADR-0016 subscription only).
- [x] 4.2 Verify each replays through the `recovered` branch.
- [x] 4.3 For any case that cannot be re-captured (dead URL / changed page), re-point or retire it DELIBERATELY and record which and why — never keep a stale cassette.

## 5. Gate

- [x] 5.1 `make check` green.
- [x] 5.2 `make arch` green.
- [x] 5.3 Production-code diff: ONE blank line removed by `ruff format` in `extractor.py`. Behaviourally inert, but recorded rather than claimed as "zero" — the claim was checked, not assumed.
- [x] 5.4 Confirm no wire goldens moved — this change must be wire-neutral.

## 6. UNPLANNED — the capture harness was dead (found during 4.1)

Re-capture could not run: `eval/_capture/capture.py` still imported
`a2kit.ldd` / `a2kit.packages.testing.null_context`, called the removed
`bootstrap_state`, and passed `browser_pool=` to a `fetch()` that takes
`browser_backend=`. The whole capture/refresh path had been broken since the
a2kit sunset (2026-07-22) and nothing in `make check` runs it, so it went
unnoticed for five days — a FIFTH dead instrument, and the reason the cassettes
were both stale and lossy: nobody could refresh them.

- [x] 6.1 Drop the dead `a2kit` imports and the retired `ldd_state_for_call` wrapper.
- [x] 6.2 Port `bootstrap_state`/`Resources` to `build_components()` + `parts.aclose()`.
- [x] 6.3 Replace `_TeePool`/`_TeePage` (the removed `BrowserPool.acquire()` API) with `_TeeBackend` over `any_browser`'s `render()`.
- [x] 6.4 Resolve the `Lazy[LlmExtractorResource]` thunk lazily in `_TeeExtractor` rather than treating it as the resource.
- [x] 6.5 FOLLOW-UP (not done here): nothing runs this harness in CI, which is why it rotted. Tracked in BACKLOG.md.
