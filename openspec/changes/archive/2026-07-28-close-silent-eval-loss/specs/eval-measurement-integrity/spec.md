## ADDED Requirements

### Requirement: an axis records why it did not score a cell

Every scoring axis SHALL record a per-cell disposition drawn from a closed set:
`scored`, `not_applicable` (the corpus entry does not ask for this axis), or
`unscored` (the axis was asked for and produced no score) carrying a reason. An
absent score alone SHALL NOT be recorded, because it cannot distinguish a system
that correctly emitted nothing from a harness that failed to read what was emitted.

#### Scenario: an axis that does not apply to a case

- **WHEN** a corpus entry does not request an axis for a cell
- **THEN** that cell's disposition for the axis is `not_applicable`
- **AND** the cell is excluded from the axis denominator

#### Scenario: an axis that was asked for and failed to score

- **WHEN** a corpus entry requests an axis and the harness produces no score for it
- **THEN** that cell's disposition is `unscored` carrying a reason
- **AND** the cell counts toward the axis denominator as an unscored cell

#### Scenario: a judge parse failure is not silence

- **WHEN** the judge for an axis raises a parse error on a cell
- **THEN** the cell's disposition is `unscored` with the parse failure as its reason,
  rather than an absent score indistinguishable from a skip

### Requirement: a reported statistic carries its denominator

Every aggregate the report renders SHALL be accompanied by the number of cells it
was computed over. A mean SHALL NOT be rendered beside a row count that includes
cells the mean excluded.

#### Scenario: a mean over a subset of rows

- **WHEN** the report renders an axis mean computed over fewer cells than the run
  contains
- **THEN** the rendered value states the number of cells the mean covers

#### Scenario: every axis renders alike

- **WHEN** the report renders the axis table
- **THEN** all axes state their coverage in the same form, so no axis's coverage is
  implied by the absence of a note

### Requirement: an axis that scored nothing is a harness failure

An axis requested on at least one cell and scored on zero cells SHALL be reported as
a failure of the harness rather than as a result. The run SHALL still write every
artifact it produced, because a bench run is expensive and its partial output is
evidence; the failure SHALL be recorded in the run artifacts and surfaced in the
process exit path.

#### Scenario: an envelope rename voids an axis

- **WHEN** an axis is requested on one or more cells and produces zero scores
- **THEN** the run reports the axis as broken, naming it
- **AND** the run's artifacts are written in full
- **AND** the outcome is distinguishable from an axis that was never requested

#### Scenario: a partially scored axis is not a failure

- **WHEN** an axis is requested on several cells and scores at least one
- **THEN** the run does not report the axis as broken
- **AND** the unscored cells remain visible in the axis coverage

### Requirement: a run declares whether its observations were independent

The run manifest SHALL record the cache mode under which the run executed, and the
harness SHALL offer a mode that bypasses the extraction cache. A repeated
measurement served from cache is one observation reported many times, and a run that
does not state its cache mode cannot be read as evidence of reproduction.

#### Scenario: the manifest states the cache mode

- **WHEN** a benchmark run completes
- **THEN** its manifest records whether the extraction cache was bypassed

#### Scenario: an independent re-measurement is available

- **WHEN** an operator needs observations that do not reuse a prior extraction
- **THEN** the harness offers a cache-bypassing mode, and a run using it is marked as
  such in its manifest
