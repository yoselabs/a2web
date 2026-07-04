## ADDED Requirements

### Requirement: retrieval_incomplete envelope field
`FetchResponse` (and the projected `AskResponse`) SHALL carry a `retrieval_incomplete` boolean that is true when the requested URL's content was not retrieved due to a wall. The field SHALL be present on the wire whenever true and MAY be omitted when false (absence means retrieval was complete).

#### Scenario: Field present on walled fetch
- **WHEN** a fetch is walled
- **THEN** the serialized envelope includes `retrieval_incomplete: true`

#### Scenario: Field absent on success
- **WHEN** a fetch succeeds
- **THEN** the envelope omits `retrieval_incomplete` (or sets it false)

### Requirement: OperatorHint severity
`OperatorHint` SHALL gain a `severity` field (at least `info` and `critical`). A `try_user_browser` hint SHALL be `critical`. Existing hints without an explicit severity default to `info` (backward-compatible).

#### Scenario: Browser hint is critical
- **WHEN** a `try_user_browser` hint is emitted
- **THEN** its `severity` is `critical`

#### Scenario: Existing hints stay info
- **WHEN** a pre-existing hint (e.g. `cookies_stale`) is emitted without an explicit severity
- **THEN** its severity defaults to `info` and existing behavior is unchanged
