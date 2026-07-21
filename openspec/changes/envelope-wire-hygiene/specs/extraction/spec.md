## ADDED Requirements

### Requirement: Empty conditional fields are absent from the MCP wire

A `query` response's optional conditional fields (`other_pages`, `headings`,
`refinement_axes`, `options`) SHALL be ABSENT from the MCP wire envelope when
empty — not present as an empty TSV string, and with no `_<name>_format`
discriminator sidecar. Absence of a conditional field is the caller's signal that
it has no content; an empty-but-present field defeats that signal.

This SHALL hold on the real MCP dispatch encoding path, not only on the CLI/JSON
path — the two paths SHALL agree on omit-empty behavior.

#### Scenario: A healthy answer omits its empty conditionals over MCP

- **WHEN** a `query` returns an answer with no `other_pages`, no `headings`, no
  `refinement_axes`, and no `options`
- **THEN** the MCP envelope contains none of those four keys and none of their
  `_<name>_format` sidecars

#### Scenario: A present conditional still renders

- **WHEN** a `query` returns a non-empty `other_pages`
- **THEN** the MCP envelope carries `other_pages` (as TSV) — only the empty case
  is omitted, never a populated one
