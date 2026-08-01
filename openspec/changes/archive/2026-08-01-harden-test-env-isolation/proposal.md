## Why

Three releases have now failed the CI gate on the same defect: the test suite reads whether the DEVELOPER'S MACHINE has an LLM available, so a test can be green on a laptop with a Claude Code session and red on a bare runner with no code difference between the two runs. 0.47.0 and 0.47.1 died on provider-selection tests; 0.48.0 died on the CLI contract goldens, where the `Extractor.extract` stub is only reached once `select_provider` returned a provider, so under `auto` with no credentials every `web query` golden silently degraded to an `llm_unavailable` payload. Each was fixed one test at a time, and none of the fixes made the next occurrence impossible.

The cost is not just a red build. A suite whose result depends on the host is not measuring the code, and the local run stops being usable as a pre-release check: the only environment that tells the truth is the one that runs after the tag is already pushed, when the fix costs a new version number.

## What Changes

- Add an autouse `conftest.py` fixture that scrubs the ambient LLM environment for EVERY test: the credential env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, and the settings-configurable key-env names) are removed, and the Claude Code session backend is forced unavailable. A test that wants a provider SHALL configure one explicitly.
- Add an opt-in `ambient_llm` marker for the few tests that genuinely intend to observe the host's real provider availability, so the intent is declared rather than inherited.
- Add a guard that fails when the scrubbing fixture is absent or has been narrowed, so a future edit cannot quietly restore host-dependence. The guard carries a non-vacuity floor, consistent with how this repo's other structural guards are written.
- Fold in the point fix already applied to `tests/contracts/test_cli_contract.py` during the 0.48.1 release, so the general mechanism subsumes it rather than sitting alongside it.
- **NOT** a change to what any production code does. Provider selection, the `auto` order, and the `llm_unavailable` degrade path are all unchanged; this change is about what the suite is allowed to read from its host.

## Capabilities

### New Capabilities

- `test-env-hermeticity`: the test suite's relationship to its host environment. Tests observe only what they configure; ambient credentials and sessions on the developer's machine are invisible by default, declared explicitly when wanted, and the property is enforced rather than remembered.

### Modified Capabilities

None. `test-layout` already requires that only deterministic checks gate `make check` and that they make no live network, browser, or LLM call, and that requirement is unchanged and still correct. This change covers a failure one step earlier: no live call is made, an availability PROBE is, and the probe's answer differs per machine. The two requirements are complementary and the new capability owns the probe half.

## Impact

- `tests/conftest.py`: gains the autouse scrubbing fixture; its fixtures already cascade to every zone per `test-layout`.
- `pyproject.toml`: registers the `ambient_llm` marker alongside the existing `browser` marker.
- `tests/architecture/`: gains the guard asserting the fixture exists and covers the full variable set.
- `tests/contracts/test_cli_contract.py`: its local provider pin becomes redundant once the general fixture lands and is reduced to an explicit configuration rather than a workaround.
- Any test that currently passes only because the host supplied a provider will start failing and must configure one explicitly. Finding those is part of the work, not a surprise afterwards.
- `docs/architecture/verification-provenance.md`: this is a fourth mechanizable guard in the same family as the three recorded there, and belongs in that list. It is the "your machine is not an oracle" case.
- No production module, no public API, no dependency change.
