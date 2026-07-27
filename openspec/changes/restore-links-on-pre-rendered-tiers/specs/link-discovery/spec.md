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

### Requirement: inline links are preserved in extracted page content

Extracted `content_md` SHALL preserve in-body anchors as markdown links. A page
whose substance IS its links SHALL NOT be rendered as prose that mentions them
without targets.

#### Scenario: a listing page's entries keep their targets

- **WHEN** a page of linked entries is extracted
- **THEN** the entries appear in `content_md` with their link targets intact
