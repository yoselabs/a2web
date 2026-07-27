## ADDED Requirements

### Requirement: HTML content extraction funnels through one canonical entry point

Content extraction from HTML SHALL go through the single canonical extractor.
Modules SHALL NOT call the underlying extraction library directly. The ban SHALL
be enforced by a test, not by convention.

The canonical extractor returns markdown, links, headings and metadata from one
off-thread parse. A direct library call returns markdown only, so every bypass
silently discards the links and headings its caller never knew it could have had
— which is exactly how the link index was lost on every pre-rendering tier. The
repo already funnels JSON parsing this way for the same reason.

#### Scenario: a module calls the extraction library directly

- **WHEN** any module outside the permitted funnel imports or calls the
  extraction library directly
- **THEN** the architecture test fails, naming the module and the canonical
  entry point to use instead

#### Scenario: the funnel guard is not vacuous

- **WHEN** the funnel guard runs
- **THEN** it asserts it inspected at least a floor number of source files, so a
  moved source root cannot make it pass by finding nothing to object to

### Requirement: anchors are carried structurally, not inlined into the body

A page's anchors SHALL reach the digest as structured link records. They SHALL
NOT be inlined into `content_md` as markdown targets in order to achieve this.

Measured 2026-07-28: the extractor's `include_links` option changes only how
`content_md` renders — the structured link list is returned either way — and
enabling it flattens a bulleted listing into a single run-on line (3 bullets to
0). The body is what the model reads; the structured links are what the digest
reads. One default parse serves both, and inlining buys nothing while costing
the body's structure.

#### Scenario: a listing page keeps its list structure

- **WHEN** a page of linked list entries is extracted by any tier
- **THEN** the entries remain distinct list items in `content_md`
- **AND** their anchors are available as structured links
