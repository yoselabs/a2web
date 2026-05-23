## MODIFIED Requirements

### Requirement: Render the record region to link-preserving markdown

The package SHALL render a located record region to markdown that preserves every link — anchor text and href — within each record. It SHALL NOT select a single "primary" link per record for the rendered markdown: all links are retained for a downstream consumer to choose from. Rendering SHALL be **depth-aware** — a flat record set renders as a flat list; a threaded record set renders with indentation reflecting the nesting depth of each record. Each record's rendered text and links SHALL be its **own scope**: the text and links of a nested child-record SHALL NOT be duplicated into its parent. Rendering SHALL operate on the bounded region subtree only, never the whole page.

The renderer SHALL **lead with the record's heading** — when the detector has populated a heading element for the record, the first rendered line is `- [heading_text](heading_link)` (or `- heading_text` when only the text is present, no link). The remaining own-scope text (excluding the heading text) and remaining own-scope links render as the record's body on subsequent indented lines. This surfaces what the detector already computed (the heading element it used to clear guard (c)) instead of flattening it into the body smush.

#### Scenario: Flat catalog renders as a flat list

- **WHEN** a flat (depth 0) record set is rendered
- **THEN** each record is a list entry carrying its slug text and every link in that record

#### Scenario: Threaded discussion renders with depth

- **WHEN** a threaded (depth > 0) record set is rendered
- **THEN** each record is indented by its nesting depth, and no record's text is duplicated into its parent

#### Scenario: Record leads with its heading link

- **WHEN** the detector has identified a heading element with text and link for the record
- **THEN** the rendered first line of the record is `- [heading_text](heading_link)` and the heading text does NOT also appear in the subsequent body smush

#### Scenario: Record without a heading link falls back to text-only lead

- **WHEN** the detector has identified a heading element with text but no own-scope anchor in the heading
- **THEN** the rendered first line of the record is `- heading_text` (no link wrapper) and the body follows on subsequent indented lines
