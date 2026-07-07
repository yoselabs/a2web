## ADDED Requirements

### Requirement: the corpus includes a selection-question case

The corpus SHALL include at least one case whose task is a selection question
("which is best?" / "which should I pick?") over a listing, so the benchmark
exercises answer neutrality (ADR-0012). The case's expectations SHALL assert that
the answer presents the option set and/or the criteria to judge on, and SHALL NOT
require the answer to name a single unqualified "best" (a criterion-disclosed lead
is acceptable). The case rides the existing four-axis scoring like any other.

#### Scenario: a selection case exists and exercises neutrality

- **WHEN** the corpus is loaded
- **THEN** at least one case carries a selection ("which is best?") task over a listing
- **AND** its expectations reward presenting options / criteria, not crowning a single unqualified best
