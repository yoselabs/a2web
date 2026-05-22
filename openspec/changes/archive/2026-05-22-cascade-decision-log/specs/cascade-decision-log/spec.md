## ADDED Requirements

### Requirement: Fetch state is an append-only observation log

One fetch SHALL accumulate its state as an append-only, immutable sequence of typed `Observation` records. Every tier attempt, quality-gate evaluation, and escalation SHALL append exactly one `Observation`; no component SHALL overwrite or mutate a prior `Observation`. An `Observation` SHALL carry at minimum: its `verdict`, its `source` (the tier / handler / gate that produced it), an `authoritative` flag (the source vouches the verdict is definitive for its domain), a relative timestamp, and structured evidence. The orchestrator SHALL NOT carry a mutable scalar `final_verdict` field — the verdict is derived, never stored.

#### Scenario: Each tier attempt appends one observation

- **WHEN** the cascade dispatches a tier and the tier returns a result
- **THEN** exactly one `Observation` is appended to the log carrying that tier's verdict and source

#### Scenario: A later observation never mutates an earlier one

- **WHEN** a downstream tier appends an observation after an upstream tier already appended one
- **THEN** the upstream observation is still present in the log, unchanged — no field of a prior observation is overwritten

#### Scenario: No mutable final-verdict slot exists

- **WHEN** static inspection walks `FetchContext`
- **THEN** there is no settable scalar `final_verdict` field — the final verdict is only obtainable by projecting the observation log

### Requirement: Final verdict is a pure total projection of the observation log

The final verdict SHALL be computed by a pure function `resolve_verdict(log) -> Verdict`, never stored. `resolve_verdict` SHALL be **total** — defined for every possible log, including the empty log — and SHALL select the verdict by an explicit precedence: any observation that is a successful gate-passing result yields `ok`; otherwise the highest-precedence failure verdict wins, where an `authoritative` observation outranks a non-authoritative one, and within each authority level a fixed `Verdict` ranking applies (definitive verdicts such as `not_found` / `paywall` / `anti_bot` outrank vague verdicts such as `length_floor` / `other`). `resolve_verdict` SHALL be **order-independent**: its result depends on the set of observations, not their arrival order.

#### Scenario: Authoritative not_found outranks a non-authoritative length_floor

- **WHEN** the log holds an authoritative `not_found` from a site handler and a non-authoritative `length_floor` from a generic tier, and no observation is gate-passing
- **THEN** `resolve_verdict` returns `not_found`

#### Scenario: A downstream gate-passing observation yields ok

- **WHEN** the log holds an earlier failure observation and a later observation that is a gate-passing success
- **THEN** `resolve_verdict` returns `ok` — a genuine recovery always wins

#### Scenario: The empty log yields a defined verdict

- **WHEN** `resolve_verdict` is called with an empty log
- **THEN** it returns a defined `Verdict` member, not an error or `None`

#### Scenario: Result is invariant under observation reordering

- **WHEN** `resolve_verdict` is called on a log and on any permutation of that log
- **THEN** both calls return the same `Verdict`

### Requirement: Escalation is decided by a pure planner over the observation log

The orchestrator's next action SHALL be chosen by a pure function `decide_next(log, url, caps) -> Action` that reads the entire observation log, the request URL, and the per-fetch caps. `decide_next` SHALL be total. The `Action` vocabulary SHALL include: `RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, and a `Continue` no-op action. `decide_next` SHALL be expressible as a decision table whose rows cover every combination of (most-recent observation kind and verdict, escalation evidence, per-fetch caps), each mapping to exactly one `Action`.

#### Scenario: A soft-block observation yields EscalateBrowser with no winning tier

- **WHEN** the log holds only failure observations (no tier produced gate-passing content) and at least one carries a soft-block / JS-required signal, and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: Browser budget exhausted yields no further EscalateBrowser

- **WHEN** the caps show the browser dispatch budget is already spent
- **THEN** `decide_next` never returns `EscalateBrowser`

#### Scenario: Every condition combination maps to exactly one action

- **WHEN** the `decide_next` decision table is checked over the full product of its input conditions
- **THEN** every combination maps to exactly one `Action` — no missing row, no conflicting rows

### Requirement: The orchestrator is a pure executor of planner actions

The orchestrator SHALL hold no escalation, rewrite, or stop policy of its own. After each tier and after the gate, it SHALL append the resulting `Observation`, call `decide_next`, and execute the returned `Action`. Every escalation, rewrite, and cascade-stop decision SHALL originate from `decide_next`.

#### Scenario: Orchestrator escalates only on a planner action

- **WHEN** a tier result would historically have triggered an inline escalation but `decide_next` returns the continue / no-op action
- **THEN** the orchestrator performs no escalation and advances to the next `TIER_ORDER` slot

### Requirement: The fetch response derives its verdict from the observation log

`FetchResponse` SHALL be built by a pure function. Its `status`, `confidence`, `narrative`, and `diagnostics_summary` SHALL be derived from `resolve_verdict(observation log)` — no mutable verdict slot feeds them. The response SHALL be identical in shape and content to the response the prior orchestrator produced for the same fetch — this change introduces no wire / envelope change.

#### Scenario: Response verdict equals the resolved verdict

- **WHEN** a fetch completes and `FetchResponse` is built
- **THEN** the verdict reflected in `status` / `diagnostics_summary` equals `resolve_verdict(log)` for that fetch's observation log
