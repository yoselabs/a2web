## ADDED Requirements

### Requirement: a partial loss on a requested axis fails the run

A run SHALL fail when a requested axis scores fewer than a stated fraction of its
requested cells. The fraction SHALL be declared, not implicit.

Failing only at zero coverage means an axis can degrade from full coverage to a
handful of cells across runs while every run exits 0. The honest denominator is
reported, but reporting is not a gate: it requires a human to notice a number
that shrank. A measurement that quietly narrows its own sample is not a
measurement.

#### Scenario: An axis below the coverage floor fails the run

- **WHEN** a requested axis scores fewer cells than the declared floor
- **THEN** the run exits non-zero and names the axis and its coverage

#### Scenario: The floor is stated in the artifact

- **WHEN** a run completes
- **THEN** the artifact records the coverage floor in force alongside each axis's
  achieved coverage
