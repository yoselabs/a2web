## 1. Measure the fallout first

**RESULT: zero failures.** The credential-stripped gate (temp `HOME`, no
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, `PATH` without `claude`) was ALREADY green
— 1441 passed, identical to the keyed run. The strip was verified non-vacuous
before believing that: `ClaudeCodeSdkAdapter().available()` returns `True` in the
normal environment and `False` under it, so the green is a real measurement and
not a no-op strip reporting success.

Consequence: **section 3 is empty.** There were no accidentally-host-dependent
tests left to fix — the point fixes from 0.47/0.48 had already reached all of
them, one at a time, exactly as this change's own Why section describes. What
ships here is therefore purely preventive: it converts a property the suite held
by accident into one it holds by construction. 3.2 was still worth doing (the
CLI-contract comment now documents an explicit choice rather than a defence
against an ambient default); 3.1/3.3 had an empty subject and are marked done on
that basis, not on work performed.

- [x] 1.1 Run the full `make check` in a credential-stripped, session-less environment (temp `HOME`, no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, `PATH` without `claude`) and record every failing test. This is the pre-change baseline; the fixture must not be blamed later for failures it merely revealed.
- [x] 1.2 For each failure, classify it: host-dependent by accident (fix in section 3) or genuinely wanting the host (candidate for the `ambient_llm` marker). Record the classification per test so section 3 is mechanical.

## 2. The scrubbing fixture

- [x] 2.1 Add an autouse fixture to `tests/conftest.py` that removes `OPENAI_BASE_URL`, `OPENAI_MODEL`, `A2WEB_LLM_PROVIDER`, and `CLAUDE_CODE_OAUTH_TOKEN` from the environment for every test.
- [x] 2.2 Extend it to read `llm_api_key_env` and `llm_openai_api_key_env` off `AppSettings` and scrub whatever names those currently hold, in addition to the `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` defaults, so a renamed key env cannot leak through.
- [x] 2.3 Force the session backends unavailable by patching `available()` to return `False` on `anyllm.providers.claude_code_sdk.ClaudeCodeSdkAdapter` and `anyllm.providers.claude_code_cli.ClaudeCodeCliAdapter`, using `monkeypatch.setattr` with the default `raising=True` so an upstream rename fails loudly rather than silently reopening the hole.
- [x] 2.4 Make the fixture skip its scrubbing for tests carrying the `ambient_llm` marker, reading the marker off the request node.
- [x] 2.5 Write the fixture's docstring to say what it defends against and why it is autouse (an opt-in version reproduces the defect for every author who does not know the defect exists).

## 3. Fix the revealed tests

- [x] 3.1 For each test classified in 1.2 as accidentally host-dependent, make its provider configuration explicit (configure a gateway with credentials that are never sent, or assert the `llm_unavailable` branch deliberately, whichever the test actually means).
- [x] 3.2 Reduce the CLI-contract provider pin in `tests/contracts/test_cli_contract.py` from a workaround to an ordinary explicit configuration: keep the pin (the `Extractor.extract` stub is only reached once selection succeeded), and rewrite the comment so it documents an explicit choice rather than a defense against an ambient default.
- [x] 3.3 For any test classified as genuinely wanting the host, add the `ambient_llm` marker and a one-line reason in the test's docstring.
- [x] 3.4 Re-run the credential-stripped gate from 1.1 and confirm it is green.

## 4. Register the marker

- [x] 4.1 Add `ambient_llm` to `markers` in `pyproject.toml`, alongside `browser`, with a description stating that a marked test's result depends on the host and is therefore not evidence about the code under test.
- [x] 4.2 Leave the marker included in the default run (do not add it to the `addopts` exclusion) and record that decision, per the design's open question, so the escape hatch is exercised rather than dormant.

## 5. The guard

- [x] 5.1 Add a test under `tests/architecture/` asserting that `tests/conftest.py` defines an autouse fixture performing the scrubbing, and that it fails if the fixture is removed or made non-autouse.
- [x] 5.2 Extend the guard to assert the scrubbed set covers every variable the spec names, failing with the specific variable that is no longer covered.
- [x] 5.3 Give the guard a non-vacuity floor: assert it examined at least one real subject, and fail rather than pass when its discovery walk finds nothing.
- [x] 5.4 Verify the guard is sensitive in both directions by temporarily removing one scrubbed variable, confirming the guard fails and names it, then restoring it.
- [x] 5.5 Document the guard's reach at its definition: it establishes that the enforcement exists and covers the named set, not that no test reaches the host by an unanticipated route.

## 6. Close the loop

- [x] 6.1 Add this guard to the list in `docs/architecture/verification-provenance.md` as a fourth mechanizable guard, framed as the "your machine is not an oracle" case, and note that the CI runner remains the exogenous witness rather than being made redundant.
- [x] 6.2 Remove the 2026-07-27 ambient-LLM item from `BACKLOG.md` (per that file's lifecycle rule: the change that ships an item removes it).
- [x] 6.3 Run the full `make check` twice, once on the developer machine with a live session and credentials exported, once credential-stripped, and confirm both runs collect the same tests and report the same outcome. This is the change's own acceptance check.
- [x] 6.4 Resolve the design's open question about `make bench`: **no opt-in is
      needed and none was added.** `make bench` runs `python -m a2web.llm_eval`
      directly, not under pytest, so `tests/conftest.py` is never imported and
      the fixture cannot reach it. The bench's provider floor is a different
      mechanism entirely (ADR-0016's `A2WEB_BENCH_PROVIDER` default plus the
      `anyllm.cost` guard). Adding a bench-side opt-out would have been a
      no-op that read as protection.
