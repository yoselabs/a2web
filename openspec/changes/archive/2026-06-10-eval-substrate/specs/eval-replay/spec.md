## ADDED Requirements

### Requirement: replay freezes egress and runs the real pipeline above it

The eval substrate SHALL replay a fetch by reading frozen bytes at each tier's **egress
boundary** while running the orchestrator, gate, extraction ladder, and escalation logic
unmodified. Replay SHALL NOT freeze or stub the produced `FetchResponse`, the routing
decision, or any logic above the egress. The frozen egress points SHALL be: the
`http_fetch.fetch_bytes` outcome (raw/jina/archive HTTP), the `BrowserPool`-rendered DOM
(browser tier), and the `LlmExtractorResource` provider response (LLM).

#### Scenario: escalation logic runs against frozen inputs

- **WHEN** a replayed case escalates from the raw tier to the browser tier
- **THEN** the real escalation decision runs, and the browser tier is served the frozen
  rendered DOM from the cassette — not a canned `FetchResponse`

#### Scenario: replay is bit-reproducible

- **WHEN** the same case is replayed twice with unchanged code and fixtures
- **THEN** the produced answer, tier path, and token cost are byte-for-byte identical

### Requirement: the LLM is a recorded egress

In full-replay mode the LLM provider call SHALL be served from a recorded request/response
in the cassette rather than a hand-authored fake, so the produced answer is reproduced
exactly and the deterministic axes (contract shape, token cost, tier path) can assert exact values.

#### Scenario: a recorded LLM response reproduces the answer exactly

- **WHEN** a case with a recorded LLM response is replayed
- **THEN** the extracted answer equals the recorded answer byte-for-byte, and the reported
  token cost equals the recorded token cost

### Requirement: interception is test-side and adds no product surface

Replay interception SHALL be implemented in the test and `eval/` layer only: DI-provided
resources (`BrowserPool`, `LlmExtractorResource`) intercepted test-side — wrapped as
`Lazy[T]` cassette resources at the `fetch()`/tool seam, or via the in-process test
client's `override` — and the `fetch_bytes` chokepoint via a single centralized patch that
rebinds every import site. The substrate SHALL NOT add an `a2web` CLI verb, an MCP tool, or
any eval-specific code to the shipped product surface.

#### Scenario: no product CLI/MCP verb is added

- **WHEN** the shipped `a2web` CLI and MCP tool list is inspected
- **THEN** it contains no `eval`/`capture`/`replay`/`refresh` verb or tool

### Requirement: an un-frozen tier fails loudly, never falls through to the network

Replay SHALL raise a structured failure when a replayed case exercises a tier for which the
cassette has no frozen entry — naming the case, the missing tier, and the one-command fix
(`make eval-refresh CASE=<id>`). It SHALL NOT fall through to a live network or browser call.

#### Scenario: a missing browser snapshot is a red, fixable test

- **WHEN** a routing change makes a case escalate to the browser tier but no rendered
  snapshot was frozen for it
- **THEN** replay fails with a message naming the case, `tier=browser`, and the refresh command,
  and makes no network or browser call
