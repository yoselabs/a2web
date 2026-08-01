## Context

`select_provider` (`src/a2web/llm_resource.py`) walks a preference order and asks each candidate backend whether it is usable. Two of those probes read state that belongs to the machine rather than to the code:

- `AnthropicApiAdapter.available()` and `OpenAiCompatibleAdapter.available()` read env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` as the explicit-gateway intent signal that reorders `auto`);
- `ClaudeCodeSdkAdapter.available()` reads `CLAUDE_CODE_OAUTH_TOKEN`, then the on-disk credential file, then the existence of a macOS Keychain item. This one is not reachable by scrubbing the environment alone, which is exactly why it keeps surviving the point fixes.

When every probe says no, `select_provider` returns `None` and callers degrade to an `llm_unavailable` payload. That degrade path is correct in production and is not changing. The defect is that the suite lets the host decide which branch runs, so the same commit produces different results on a laptop and a runner. Three releases have failed this way (0.47.0, 0.47.1, 0.48.0), each fixed one test at a time.

`tests/conftest.py` already sits at the `tests/` root and its fixtures cascade to every zone (`test-layout`), so there is a single place to enforce this. `pyproject.toml` already registers one opt-in marker (`browser`) with the same shape as the one this change needs.

## Goals / Non-Goals

**Goals:**

- A test's result depends on the code under test and the configuration it makes explicit, never on the developer's shell or login state.
- Local `make check` becomes usable as a pre-release check: a green local run predicts a green gate.
- The property survives future edits, rather than depending on everyone remembering it.
- The escape hatch exists and is declared, so a test that genuinely wants the host says so.

**Non-Goals:**

- No change to production behavior. `auto` ordering, the gateway-first reorder, and the `llm_unavailable` degrade are untouched.
- Not an attempt to prove that no test reads the host by any route. The guard covers the named variable set and the session backend; it cannot cover routes nobody anticipated, and this change does not pretend otherwise (see `docs/architecture/verification-provenance.md` on where CI's authority ends).
- Not a sandbox. Tests can still read the filesystem and the rest of the environment; the scope is LLM availability, which is the axis that has actually broken releases.
- Not a fix for the browser tier's analogous problem. `browser` already has its own marker and its own release-gate lane.

## Decisions

**Scrub in one autouse fixture in `tests/conftest.py`, not per-test.** The defect is that a test author has to KNOW about ambient availability to defend against it, and the three failures were each written by someone who did not. An opt-in fixture reproduces that exact shape for every future test. Autouse at the root inverts it: the safe state is inherited and the unsafe one is declared. Alternative considered: a `pytest` plugin or a `-p` hook, which would work identically but adds a distribution surface for a property that only this repo's suite needs.

**Force the session backend unavailable by patching `available()` on the anyllm adapters, not by faking the host.** The alternative is to set `HOME` to a temp dir and strip `PATH`, which is what I did by hand to reproduce the 0.48.0 failure. It works, but it is a blunt instrument that breaks unrelated tests reading `HOME`, and on macOS it does not cover the Keychain probe — the reproduction only worked because the fake `HOME` also hid the credential file. Patching the two adapters (`ClaudeCodeSdkAdapter`, `ClaudeCodeCliAdapter`) targets exactly the seam that varies. `available()` is documented public surface on those classes, and `monkeypatch.setattr` raises when the attribute is absent, so an upstream rename fails loudly at the patch rather than silently reopening the hole.

**Derive the scrubbed env-var set from the settings, not from a hardcoded list.** `llm_api_key_env` and `llm_openai_api_key_env` are configurable, so a hardcoded `["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]` would miss a renamed key env and reintroduce the defect for exactly the deployment that customized it. The fixture reads the current values off `AppSettings` and scrubs those in addition to the fixed names (`OPENAI_BASE_URL`, `OPENAI_MODEL`, `A2WEB_LLM_PROVIDER`, `CLAUDE_CODE_OAUTH_TOKEN`).

**The guard asserts on the fixture's coverage, not on test outcomes.** The tempting guard is "run the suite twice, once scrubbed, once not, and diff" — genuinely stronger, and far too slow to gate every commit. The affordable guard checks that the autouse fixture exists, is autouse, and covers the named variable set, with a non-vacuity floor so it cannot pass by discovering nothing. This matches how `test-fidelity`'s double-discovery check and the boundary-rule check in `enforcement-integrity` are already written, so it is a familiar shape in this repo rather than a new pattern. Its limit is stated at the definition: it proves the enforcement exists, not that no unanticipated route survives.

**Reduce the 0.48.1 CLI-contract pin to an explicit configuration rather than deleting it.** That test genuinely needs a provider to exist so the `Extractor.extract` stub is reached; scrubbing alone would leave it selecting nothing and degrading. What changes is its status: it stops being a workaround compensating for an ambient default and becomes an ordinary explicit configuration, which is what the requirement says. Deleting it outright would break the goldens again.

**Find the currently-host-dependent tests by running the gate scrubbed, before writing the guard.** Any test passing today only because the host supplied a provider will start failing. That set is unknown until measured, and measuring it is cheap (one gate run). Doing it first keeps the fixture and the fallout in the same change instead of discovering the fallout at the next release.

## Risks / Trade-offs

**The scrub is incomplete in a way nobody predicted** → The guard covers the named set only. Mitigation is the same one the repo already relies on for this class: state the limit where the guard is defined, and treat the CI runner (which has no credentials by construction) as the exogenous witness. This change makes the laptop match the runner; it does not make the runner redundant.

**Patching a third-party method couples the suite to anyllm's internals** → `available()` is public, documented surface, not an underscore-private. `monkeypatch.setattr` with the default `raising=True` turns an upstream rename into an immediate loud failure at every test, which is the correct direction. The risk of the alternative (silently no longer scrubbing) is strictly worse.

**A test that legitimately needs the host gets marked, and then its result is host-dependent again** → That is the intended trade, made visible. The marker registration states plainly that a marked test's result is not evidence about the code. If the marked set grows beyond a handful, that is a signal worth revisiting, not a silent regression.

**Fixture ordering: a test that sets credentials in its own fixture could run before or after the scrub** → Autouse fixtures at the root run before test-local fixtures that do not depend on them, so a test-local explicit configuration lands after the scrub and wins, which is the behavior we want. The CLI contract gate is the worked example and will demonstrate it.

## Migration Plan

Single change, no deployment surface. Order matters:

1. Land the fixture and run the full gate scrubbed to enumerate the fallout.
2. Fix each host-dependent test by making its provider configuration explicit.
3. Reduce the CLI-contract pin to an explicit configuration.
4. Add the marker registration and the guard last, so the guard is written against a suite that already satisfies it.

Rollback is deleting the fixture; nothing else depends on it. No version bump is required on its own — this rides out with the next change that alters runtime behavior, since the image would otherwise be behaviorally identical.

## Open Questions

- Should the `ambient_llm` marker also be excluded from the default run (as `browser` is via `addopts`), or merely declared? Leaning toward declared-only: the marked set is expected to be near-empty, and excluding it by default would mean the escape hatch is never exercised. Resolve when the first genuine marked test appears.
- Does `make bench` (live LLMs, the exogenous witness lane) need to opt out wholesale? It runs outside `make check` and legitimately wants real providers. Likely a single blanket opt-in at that lane's conftest rather than per-test markers; confirm when the fixture lands.
