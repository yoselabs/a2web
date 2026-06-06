## ADDED Requirements

### Requirement: The record text projection preserves node boundaries

When assembling a record's own-scope text, the package SHALL preserve the
boundaries between distinct DOM text nodes so that adjacent-but-semantically-
distinct values cannot fuse into a single token. Concatenating descendant text
fragments without a separator (the value-blind projection ADR-0003 forbids) is
prohibited: a discount badge abutting a price, or any two adjacent inline
values, SHALL remain distinguishable in the projected text. This SHALL be a
general rule applied to all records on all sites — no site-, field-, currency-,
or price-specific special-casing.

#### Scenario: Adjacent inline values do not fuse

- **WHEN** a record contains sibling inline elements with no intervening
  whitespace text node (e.g. `<del>890 TL</del><span>%21</span><span>700 TL</span>`)
- **THEN** the projected record text keeps the values separated (e.g.
  `890 TL`, `%21`, and `700 TL` are distinguishable) and never produces a fused
  token such as `890 TL%21700`

#### Scenario: Separation is general, not value-aware

- **WHEN** the projection separates adjacent nodes
- **THEN** it does so for every adjacent node pair regardless of content, with
  no branch that inspects whether a fragment looks like a price, percentage, or
  currency

### Requirement: The record projection preserves answer-bearing markup

The package SHALL preserve strikethrough markup (`<del>`, `<s>`, `<strike>`)
across the record→extractor boundary by marking the struck text in the
projected markdown (markdown strikethrough `~~...~~`), so a downstream extractor
can distinguish a superseded value (e.g. an original/list price that has been
crossed out) from the operative one (e.g. the current sale price). Bare-text
flattening that erases this distinction is prohibited.

#### Scenario: A struck-through list price is recoverable

- **WHEN** a record contains a strikethrough original price and a live sale
  price (e.g. `<del>890 TL</del>` … `700 TL`)
- **THEN** the projected record text marks the struck value (`~~890 TL~~`) so
  the original price is distinguishable from the sale price, rather than both
  appearing as undifferentiated text
