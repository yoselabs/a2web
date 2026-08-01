## ADDED Requirements

### Requirement: A handler rendering a tree bounds depth and node count

A handler that renders a recursive structure from upstream data SHALL bound both
the recursion depth and the total number of nodes rendered. The upstream data is
untrusted: its shape is chosen by the remote service, not by a2web.

The bound SHALL apply on EVERY recursive path, including paths that skip a node
and recurse into its children. A path that recurses without advancing the depth
counter defeats a depth cap entirely, which is the current shape of the
deleted-comment branch in the Hacker News handler.

Where a bound truncates the render, the handler SHALL declare the truncation
rather than emit a silently shortened tree — a caller that never sees the body
cannot tell a bounded render from a complete one.

#### Scenario: A deep tree is bounded

- **WHEN** upstream data nests deeper than the configured depth bound
- **THEN** the render stops at the bound and does not exhaust the interpreter's
  recursion limit

#### Scenario: A skip path still advances depth

- **WHEN** a node is skipped (deleted, empty) and its children are rendered in
  its place
- **THEN** the depth counter advances, so the bound still terminates the walk

#### Scenario: Truncation is declared

- **WHEN** a depth or count bound truncates the rendered tree
- **THEN** the output states that it was truncated, per the withhold-nothing-
  silently invariant

#### Scenario: Every tree-rendering handler carries the bound

- **WHEN** a handler renders a recursive structure without a depth bound
- **THEN** the offline suite fails, naming that handler
