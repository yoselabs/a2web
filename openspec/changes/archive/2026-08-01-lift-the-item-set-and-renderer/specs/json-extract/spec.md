## ADDED Requirements

### Requirement: Structured-data rendering has one table renderer and one retention policy

The structured-data renderer SHALL have one implementation of table rendering,
with one declared cell cap and one declared row cap, and every renderer path
SHALL use it.

Two table renderers twelve lines apart, with different caps and identical
escaping and header shape, are one function that was copied. The divergence in
caps is not a design decision — it is the evidence that they are not maintained
as one thing.

The renderer SHALL have one stated field-retention policy. Where the policy is
default-keep, on the stated grounds that an allowlist silently loses an
unanticipated answer-bearing field, an allowlist elsewhere in the same renderer
contradicts it and SHALL be either removed or documented as a deliberate,
reasoned exception.

Every cap in the renderer SHALL be named at a declaration site. A cap repeated as
a bare literal at several sites, with a comment instructing a reader to keep them
in sync manually, is a defect awaiting the first reader who does not.

#### Scenario: One table renderer serves every path

- **WHEN** any structured-data shape is rendered as a table
- **THEN** it is rendered by the single table renderer with the declared caps

#### Scenario: A retention exception is reasoned

- **WHEN** a renderer path restricts fields rather than keeping them by default
- **THEN** the restriction is documented with its reason, or removed

#### Scenario: Caps are named

- **WHEN** a rendering cap is applied
- **THEN** it reads from a named declaration, not a repeated literal
