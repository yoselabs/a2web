## ADDED Requirements

### Requirement: The test suite SHALL NOT observe ambient LLM availability

A test that reads whether the HOST has an LLM available is measuring the machine, not the code. Its result changes with the developer's shell and login state, so a green local run stops being evidence about the change under test.

Every test SHALL run with the ambient LLM environment scrubbed. Scrubbing SHALL cover, at minimum:

- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (the defaults of `llm_api_key_env` and `llm_openai_api_key_env`), plus whatever env-var names those settings currently name, so a renamed key env is scrubbed too rather than leaking through;
- `OPENAI_BASE_URL` and `OPENAI_MODEL`, which together are the explicit-gateway intent signal that reorders `auto`;
- `A2WEB_LLM_PROVIDER`, so an exported pin on the developer's shell cannot change which order the suite exercises;
- the Claude Code session backend, which is available on a developer machine with a live session and unavailable on a runner. Scrubbing env vars alone is insufficient here: the session is discovered through the CLI and its state on disk, not through the environment.

A test that needs a provider SHALL configure one explicitly. The scrubbed state is the default that every test inherits, not a fixture each test opts into: an opt-in default reproduces the current defect for every test whose author does not know the defect exists.

#### Scenario: The same suite passes on a laptop and a bare runner

- **WHEN** the full gate runs on a machine with a live Claude Code session and exported LLM credentials, and again on a machine with neither
- **THEN** both runs collect the same tests and report the same pass/fail outcome

#### Scenario: An exported credential is invisible to a test

- **WHEN** `ANTHROPIC_API_KEY` is exported in the shell that invokes the suite
- **THEN** a test that inspects the environment or calls provider selection observes no Anthropic credential

#### Scenario: A live session does not make a session backend available

- **WHEN** the suite runs on a machine where the Claude Code CLI and a logged-in session are present
- **THEN** provider selection under `auto` does not select the session backend

#### Scenario: A renamed key env is still scrubbed

- **WHEN** the settings name a key env var other than the default
- **THEN** that variable is scrubbed as well, and the default is not scrubbed in its place

### Requirement: A test that wants the host's real providers SHALL declare it

Hermeticity by default must not become a rule that cannot be escaped, or the escape gets built ad hoc inside individual tests and the default silently erodes.

A test that genuinely intends to observe the host's real provider availability SHALL declare that intent with an explicit `ambient_llm` marker. The marker SHALL be registered in the pytest configuration alongside the existing `browser` marker, and its registration SHALL state that a so-marked test's result depends on the host and is therefore not evidence about the code under test.

Only a marked test SHALL see the unscrubbed environment. An unmarked test SHALL NOT be able to reach ambient availability by any route the scrubbing fixture controls.

#### Scenario: A marked test sees the host

- **WHEN** a test carries the `ambient_llm` marker
- **THEN** it runs against the unscrubbed environment and can observe the host's real provider availability

#### Scenario: An unmarked test cannot opt itself back in

- **WHEN** an unmarked test attempts to observe ambient availability
- **THEN** it observes the scrubbed state, because the default applied before the test body ran

### Requirement: The hermeticity property SHALL be enforced, not remembered

A property that holds only while everyone remembers it is the state this change is correcting. The scrubbing fixture is itself code that a later edit can narrow, delete, or quietly stop applying, and the resulting host-dependence would be invisible on the machine that made the edit.

A guard SHALL fail when the scrubbing is absent or has been narrowed below the variable set this capability names. The guard SHALL carry a non-vacuity floor: it SHALL assert it examined at least one real subject and SHALL fail rather than pass when its discovery walk finds nothing, so "0 violations in 0 candidates" cannot read as success.

The guard SHALL be honest about its own reach. It can establish that the scrubbing exists and covers the named set; it cannot establish that no test reads the host by some route nobody anticipated. That limit SHALL be stated where the guard is defined rather than implied away.

#### Scenario: Removing the fixture fails the gate

- **WHEN** the autouse scrubbing fixture is deleted or made non-autouse
- **THEN** the guard fails, naming the missing enforcement

#### Scenario: Narrowing the scrubbed set fails the gate

- **WHEN** a variable this capability names is dropped from the scrubbed set
- **THEN** the guard fails, naming the variable that is no longer covered

#### Scenario: The guard refuses to pass vacuously

- **WHEN** the guard's discovery walk finds no subject to examine
- **THEN** the guard FAILS rather than reporting success

### Requirement: The CLI contract gate SHALL configure its provider rather than inherit one

The CLI contract goldens stub `Extractor.extract`, but that stub is reached only after `select_provider` returned a provider. Under `auto` with no credentials, selection returns `None` and every `web query` golden degrades to an `llm_unavailable` payload, which is what failed the 0.48.0 release build.

The gate SHALL pin an explicitly configured provider with credentials that are never sent, so selection succeeds by construction and the goldens measure the CLI rather than the host. This SHALL be an explicit configuration made possible by the general hermeticity default, not a workaround layered over an ambient one: the point fix applied during the 0.48.1 release is SUBSUMED by this requirement and SHALL NOT be retained as a separate justification.

#### Scenario: The goldens match with no host credentials

- **WHEN** the CLI contract gate runs with the ambient environment scrubbed
- **THEN** every payload golden matches byte-for-byte, and none degrades to an `llm_unavailable` payload

#### Scenario: No request leaves the process

- **WHEN** the gate runs with its pinned gateway configured
- **THEN** no network call is attempted, because the extractor stub intercepts before any request
