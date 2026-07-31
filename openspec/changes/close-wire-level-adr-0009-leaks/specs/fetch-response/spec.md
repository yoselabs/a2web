## ADDED Requirements

### Requirement: A TSV-encoded list preserves every field present on any row

When a list field is encoded as a TSV block for the `content[0].text` channel,
the column set SHALL be the union of the keys of ALL rows, in first-seen order.
It SHALL NOT be derived from the first row alone.

Rows in a2web are routinely heterogeneous by design: `OperatorHint` drops
`severity` when it is the default `info` and drops `fix` when there is no
remediation step, so two hints of different severity produce two different key
sets. Deriving columns from the first row silently discards every key that row
happens not to carry.

The loss is confined to `content[0].text` — the channel the agent reads —
because `structured_content` carries the un-encoded payload. A field-presence
assertion made through `structured_content` therefore CANNOT witness this
requirement, and SHALL NOT be relied on to.

#### Scenario: A critical severity survives a preceding info hint

- **WHEN** `operator_hints` contains an `info` hint followed by a hint with
  `severity: critical`
- **THEN** the encoded TSV block carries a `severity` column, and the critical
  hint's value appears in it

#### Scenario: Rows with disjoint keys all round-trip

- **WHEN** a TSV-encoded list contains rows whose key sets differ
- **THEN** every key present on any row appears as a column, and a row lacking
  that key renders an empty cell rather than shifting its remaining values

#### Scenario: The witness reads the agent's channel

- **WHEN** a test asserts that a field survives TSV encoding
- **THEN** it reads `content[0].text`, because an assertion over
  `structured_content` passes whether or not the encoder preserved the field
