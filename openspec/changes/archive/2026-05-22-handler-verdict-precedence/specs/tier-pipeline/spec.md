## ADDED Requirements

### Requirement: Site handler not_found takes precedence over a downstream failure verdict

A site handler returning `Verdict.not_found` is the most authoritative negative signal in the pipeline — the site expert has confirmed the content is gone. When a site handler returns `Verdict.not_found` during the tier loop AND the fetch ultimately fails (no tier produces gate-passing content), the orchestrator SHALL report `not_found` as the final response verdict, overriding any vaguer failure verdict (`length_floor`, `other`) produced by a downstream generic tier.

This precedence SHALL apply only when the fetch fails. When a downstream tier produces real, gate-passing content (final verdict `ok`), that success SHALL stand unchanged — the precedence rule never overrides a genuine recovery. The rule SHALL be scoped to `not_found`; transient handler verdicts (`rate_limited`, `timeout`, `connection_error`) are not covered.

#### Scenario: Deleted page — handler not_found survives a downstream length_floor

- **WHEN** a site handler returns `Verdict.not_found`, then the raw tier returns HTTP 200 with a thin sub-length-floor body and the gate verdict is `length_floor`
- **THEN** the final `FetchResponse` carries verdict `not_found` (not `length_floor`), and `status` is `failed`

#### Scenario: Downstream recovery still wins over a handler not_found

- **WHEN** a site handler returns `Verdict.not_found`, then a downstream tier returns gate-passing content (final verdict `ok`)
- **THEN** the final `FetchResponse` carries `status` `ok` — the precedence rule does not override the recovery

#### Scenario: No handler not_found leaves the failure verdict untouched

- **WHEN** no site handler returned `Verdict.not_found` during the fetch and the fetch fails with `length_floor`
- **THEN** the final `FetchResponse` carries verdict `length_floor` — the precedence rule does not fire
