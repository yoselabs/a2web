## ADDED Requirements

### Requirement: A fetch carries a total deadline

A fetch SHALL carry a single deadline bounding the whole pipeline — every tier,
every escalation, and extraction — not merely each hop independently. The
deadline SHALL be operator-configurable.

Per-hop timeouts do not compose into a bound. a2web's ladder can walk site
handler, raw, jina, archive, browser and paid tiers, each with its own timeout,
followed by an extraction; the sum has no ceiling and no operator knob.

#### Scenario: The pipeline stops at the deadline

- **WHEN** the elapsed time for a fetch reaches the configured deadline
- **THEN** no further tier or escalation is dispatched, and the fetch returns

#### Scenario: A deadline miss is a declared failure

- **WHEN** a fetch ends because its deadline expired
- **THEN** the envelope carries `status: failed`, `retrieval_incomplete: true`,
  and an operator hint naming the deadline — never a partial result presented as
  complete

#### Scenario: Remaining budget bounds the next hop

- **WHEN** a hop is dispatched with less time remaining than its own timeout
- **THEN** the hop is bounded by the remaining budget, not by its own timeout

### Requirement: Request bounds are configuration, not literals

Each timeout governing a network or provider request SHALL be reachable through
settings. A bound expressed only as a literal in a call site cannot be adjusted
by the operator running the deployed container, which is the only party who
knows the latency of their own network.

#### Scenario: An operator shortens a bound without a code change

- **WHEN** an operator sets a request bound through settings
- **THEN** the corresponding call site uses that value
