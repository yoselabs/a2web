## ADDED Requirements

### Requirement: Bounded scroll-until-stable render for listing completion

When invoked for listing completion, the browser render SHALL scroll the page in
a bounded loop to trigger infinite-scroll / lazy-load, terminating when the
parsed record count stops growing across a scroll step OR a scroll cap
(`scroll_cap`) / time budget (`scroll_budget_s`) is reached — whichever comes
first — and keeping the largest snapshot. Termination SHALL NOT require an item
oracle. This generalises the existing single-shot, host-seed-gated scroll into a
completion-driven loop; when not invoked for completion, render behaviour is
unchanged.

#### Scenario: Scroll stops when the count stabilises

- **WHEN** a completion render scrolls and the record count is unchanged across a step
- **THEN** scrolling stops and the largest snapshot is returned

#### Scenario: Scroll stops at the cap

- **WHEN** a completion render reaches `scroll_cap` scrolls or `scroll_budget_s` before the count stabilises
- **THEN** scrolling stops and the largest snapshot so far is returned

#### Scenario: Non-completion render is unchanged

- **WHEN** the browser tier renders for a wall/obstacle (not listing completion)
- **THEN** the existing single-render behaviour applies with no completion scroll loop
