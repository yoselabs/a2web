## 1. Measure the fallout first

- [ ] 1.1 Run the full `make check` in a credential-stripped, session-less environment (temp `HOME`, no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, `PATH` without `claude`) and record every failing test. This is the pre-change baseline; the fixture must not be blamed later for failures it merely revealed.
- [ ] 1.2 For each failure, classify it: host-dependent by accident (fix in section 3) or genuinely wanting the host (candidate for the `ambient_llm` marker). Record the classification per test so section 3 is mechanical.

## 2. The scrubbing fixture

- [ ] 2.1 Add an autouse fixture to `tests/conftest.py` that removes `OPENAI_BASE_URL`, `OPENAI_MODEL`, `A2WEB_LLM_PROVIDER`, and `CLAUDE_CODE_OAUTH_TOKEN` from the environment for every test.
- [ ] 2.2 Extend it to read `llm_api_key_env` and `llm_openai_api_key_env` off `AppSettings` and scrub whatever names those currently hold, in addition to the `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` defaults, so a renamed key env cannot leak through.
- [ ] 2.3 Force the session backends unavailable by patching `available()` to return `False` on `anyllm.providers.claude_code_sdk.ClaudeCodeSdkAdapter` and `anyllm.providers.claude_code_cli.ClaudeCodeCliAdapter`, using `monkeypatch.setattr` with the default `raising=True` so an upstream rename fails loudly rather than silently reopening the hole.
- [ ] 2.4 Make the fixture skip its scrubbing for tests carrying the `ambient_llm` marker, reading the marker off the request node.
- [ ] 2.5 Write the fixture's docstring to say what it defends against and why it is autouse (an opt-in version reproduces the defect for every author who does not know the defect exists).

## 3. Fix the revealed tests

- [ ] 3.1 For each test classified in 1.2 as accidentally host-dependent, make its provider configuration explicit (configure a gateway with credentials that are never sent, or assert the `llm_unavailable` branch deliberately, whichever the test actually means).
- [ ] 3.2 Reduce the CLI-contract provider pin in `tests/contracts/test_cli_contract.py` from a workaround to an ordinary explicit configuration: keep the pin (the `Extractor.extract` stub is only reached once selection succeeded), and rewrite the comment so it documents an explicit choice rather than a defense against an ambient default.
- [ ] 3.3 For any test classified as genuinely wanting the host, add the `ambient_llm` marker and a one-line reason in the test's docstring.
- [ ] 3.4 Re-run the credential-stripped gate from 1.1 and confirm it is green.

## 4. Register the marker

- [ ] 4.1 Add `ambient_llm` to `markers` in `pyproject.toml`, alongside `browser`, with a description stating that a marked test's result depends on the host and is therefore not evidence about the code under test.
- [ ] 4.2 Leave the marker included in the default run (do not add it to the `addopts` exclusion) and record that decision, per the design's open question, so the escape hatch is exercised rather than dormant.

## 5. The guard

- [ ] 5.1 Add a test under `tests/architecture/` asserting that `tests/conftest.py` defines an autouse fixture performing the scrubbing, and that it fails if the fixture is removed or made non-autouse.
- [ ] 5.2 Extend the guard to assert the scrubbed set covers every variable the spec names, failing with the specific variable that is no longer covered.
- [ ] 5.3 Give the guard a non-vacuity floor: assert it examined at least one real subject, and fail rather than pass when its discovery walk finds nothing.
- [ ] 5.4 Verify the guard is sensitive in both directions by temporarily removing one scrubbed variable, confirming the guard fails and names it, then restoring it.
- [ ] 5.5 Document the guard's reach at its definition: it establishes that the enforcement exists and covers the named set, not that no test reaches the host by an unanticipated route.

## 6. Close the loop

- [ ] 6.1 Add this guard to the list in `docs/architecture/verification-provenance.md` as a fourth mechanizable guard, framed as the "your machine is not an oracle" case, and note that the CI runner remains the exogenous witness rather than being made redundant.
- [ ] 6.2 Remove the 2026-07-27 ambient-LLM item from `BACKLOG.md` (per that file's lifecycle rule: the change that ships an item removes it).
- [ ] 6.3 Run the full `make check` twice, once on the developer machine with a live session and credentials exported, once credential-stripped, and confirm both runs collect the same tests and report the same outcome. This is the change's own acceptance check.
- [ ] 6.4 Resolve the design's open question about `make bench`: confirm whether that lane needs a blanket opt-in at its own conftest, and implement it if so.
