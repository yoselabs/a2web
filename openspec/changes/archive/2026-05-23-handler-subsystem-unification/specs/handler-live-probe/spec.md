## ADDED Requirements

### Requirement: make handler-probe runs a live end-to-end check per handler

The project SHALL provide a `make handler-probe` target that, for every handler in `_HANDLERS`, performs one real network fetch against a representative URL and asserts `verdict == Verdict.ok` AND `pre_rendered.content_md` is non-empty. The target SHALL NOT be included in `make check`. The target SHALL NOT spend LLM quota — `fetch_raw`-equivalent only, no `ask=`.

#### Scenario: Probe asserts handler end-to-end against the real host

- **WHEN** `make handler-probe` is invoked
- **THEN** for every registered handler, a real network fetch occurs against the handler's representative URL and the probe exits non-zero if any handler returns `verdict != Verdict.ok` or empty `pre_rendered.content_md`

#### Scenario: Probe is not part of make check

- **WHEN** `make check` is invoked
- **THEN** the handler-probe target does NOT execute, and `make check` remains offline and deterministic

#### Scenario: Adding a handler adds a probe target URL

- **WHEN** a new handler is registered in `_HANDLERS`
- **THEN** the probe map MUST include a representative URL for it; a missing entry SHALL fail the probe target loudly (not silently skip)

### Requirement: Probe findings record the transport method

A probe finding recorded in design / proposal docs (or in a handler module comment) SHALL name the transport method that produced the result — `curl_cffi-impersonated`, `httpx-anonymous`, `with-cookies`, `with-auth`, etc. — not only the HTTP outcome ("200 JSON"). A handler implementation SHALL invoke a transport at least as strong as the one the probe used; it SHALL NOT silently substitute a weaker stack.

#### Scenario: Probe finding without method is incomplete

- **WHEN** a design or proposal records only "the API returns 200 JSON anonymously" without naming the transport method
- **THEN** the finding is incomplete; reviewers SHALL request the method before accepting the handler

#### Scenario: Handler implementation matches the probed transport

- **WHEN** a probe finding records `curl_cffi-impersonated, 200 JSON`
- **THEN** the handler implementation SHALL invoke the shared `handler-transport` primitive (which provides that transport) and SHALL NOT construct a weaker client
