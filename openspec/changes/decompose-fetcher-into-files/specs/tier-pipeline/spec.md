## ADDED Requirements

### Requirement: Escalation returns a retry signal rather than invoking downstream stages

An escalation path — archive, browser, or paid — that obtains new content SHALL
return a signal to the pipeline rather than calling comprehension, sufficiency,
or answer stages itself.

Every retrieval SHALL reach comprehension and sufficiency by the same path. When
escalation calls forward, each escalator chooses its own re-entry point, and a
stage is skipped whenever one escalator's choice differs from another's. Five
install sites running four different sequences is the observed result, and the
same skip has been repaired one path at a time four times.

A stage SHALL NOT be reachable by direct call from a retrieval path. What is not
callable cannot be skipped.

#### Scenario: An escalated retrieval passes through every stage

- **WHEN** an escalation path obtains new content
- **THEN** that content passes through comprehension and sufficiency by the same
  path as a tier-loop win

#### Scenario: An escalator does not call a downstream stage

- **WHEN** an escalation path completes
- **THEN** it returns a signal, and invokes no comprehension, sufficiency, or
  answer stage directly

### Requirement: Retrieval results are installed through one chokepoint

The fields describing a retrieval result — body, content type, final URL, tier
used, pre-rendered payload, status code — SHALL be written through a single
install operation taking a typed install value.

These fields are one fact about one retrieval. Written from several sites they
drift, and the drift is invisible: an install that omits one field produces a
context that is internally inconsistent rather than obviously wrong. The content
half of this copy was already unified after it caused a live defect; the
transport half was explicitly excluded and remains split.

Unifying the writes does not unify the sequence around them. Both are required:
the chokepoint makes the fields consistent, the single pipeline path makes the
ordering consistent.

#### Scenario: A new retrieval path installs through the chokepoint

- **WHEN** any path produces a retrieval result
- **THEN** it installs via the single install operation

#### Scenario: An incomplete install is a type error

- **WHEN** an install omits a field of the result
- **THEN** it fails at construction rather than producing a partially updated
  context
