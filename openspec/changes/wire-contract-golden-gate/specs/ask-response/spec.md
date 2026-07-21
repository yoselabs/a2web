## ADDED Requirements

### Requirement: The wire contract is frozen as golden snapshots captured through a real MCP client

The MCP wire surface SHALL be frozen as golden artifacts captured by driving the
production server with a real MCP client. Snapshots SHALL NOT be derived from any
test-only re-encoding path, from a framework-private schema computation, or from
a formatter invoked directly. The governing rule: if a byte does not come out of
the real client, it is not a contract byte.

The frozen surface SHALL cover: the advertised tool list (names, descriptions,
input schemas, output schemas, annotations, titles), the response of each
scenario on BOTH the text-content channel and the structured-content channel, the
error responses, and the mid-call log-notification stream.

#### Scenario: The tool list is frozen

- **WHEN** the wire gate runs against the built server
- **THEN** the advertised tool list matches the golden exactly, including
  descriptions and input schemas

#### Scenario: Both response channels are frozen per scenario

- **WHEN** a scenario is captured
- **THEN** both the text-content channel and the structured-content channel are
  recorded, and the text channel is stored as an opaque string that is never
  parsed or re-serialized before comparison

#### Scenario: Errors are part of the frozen surface

- **WHEN** an error scenario is captured
- **THEN** the error flag, the raw text content, and the structured content are
  all frozen

### Requirement: The wire gate cannot pass vacuously

The wire gate SHALL carry assertions that fail when a fixture stops producing
meaningful content, so a degenerate or empty capture is a failure rather than a
trivially-passing comparison. Scrubbing of volatile values SHALL be confined to
the structured-content channel and SHALL NOT be applied inside the frozen raw
text, because a substitution inside the frozen string is how a real difference
hides.

#### Scenario: A degenerate capture fails

- **WHEN** a golden artifact is empty, or a captured text channel is trivial
- **THEN** the gate fails rather than reporting a match

#### Scenario: The advertised tool count is asserted

- **WHEN** the gate runs
- **THEN** it asserts the exact expected number and names of advertised tools

#### Scenario: Raw text is never scrubbed

- **WHEN** volatile values are normalized before comparison
- **THEN** normalization applies only to the structured-content channel, and the
  raw text channel is compared verbatim

### Requirement: Wire changes are accepted only with a recorded reason

Re-blessing a golden SHALL require an explicit reason identifier, and the
resulting difference SHALL be appended to a durable deltas record under that
identifier. A re-bless with no reason SHALL be rejected when goldens already
exist. This distinguishes a deliberate, explained wire change from an accidental
regression.

#### Scenario: An unexplained re-bless is rejected

- **WHEN** a re-bless is attempted with no reason identifier and goldens exist
- **THEN** the operation is rejected

#### Scenario: An explained change is recorded

- **WHEN** a re-bless is performed with a reason identifier
- **THEN** the new golden is written and the difference is appended to the deltas
  record under that identifier

### Requirement: Adversarial cell content is part of the frozen surface

The frozen scenarios SHALL include tabular cell values containing a double quote,
an interior newline, an interior tab, and a backslash. These are the characters
whose encoding differs between codecs, so freezing them makes a later codec
change produce a bounded, reviewable difference instead of an unbounded one.

#### Scenario: Adversarial characters are captured

- **WHEN** the goldens are captured
- **THEN** at least one scenario contains a cell with a double quote, one with an
  interior newline or tab, and one with a backslash

### Requirement: A populated off-page index survives to the text channel

For any response whose model carries a non-empty off-page index, the index target
SHALL be present in the text-content channel. This is asserted directly, not via
a golden comparison, because a golden captured against a defective encoder would
freeze the defect and a faithful reproduction of that encoder would then pass.

#### Scenario: The index reaches the caller

- **WHEN** a response model carries a non-empty off-page index
- **THEN** the index target appears in the text-content channel
