## ADDED Requirements

### Requirement: try_url URLs are rehydrated, never model-typed

`try_url` entries SHALL carry hrefs rehydrated from the closed digest set (owned by `link-affordances`), not URLs typed by the extractor. An entry whose handle is absent from the digest SHALL NOT appear. The prior "URL must appear verbatim in content" instruction is superseded: the model references a handle, and the server supplies the real URL.

#### Scenario: try_url carries a real anchor href

- **WHEN** the extractor selects handle `{{3}}` for a drilldown
- **THEN** the `try_url` entry's URL is the real href for handle 3

#### Scenario: Hallucinated URL cannot appear

- **WHEN** the extractor emits a handle not in the digest
- **THEN** no corresponding `try_url` entry is produced

### Requirement: try_url entries flag off-domain targets

Each `try_url` entry SHALL indicate whether its target is off the fetched page's domain, so the caller can treat off-domain suggestions (whose anchor labels are attacker-controllable) with appropriate caution.

#### Scenario: Off-domain flag present

- **WHEN** a `try_url` target is on a different registrable domain than the fetched page
- **THEN** the entry is marked off-domain on the wire

### Requirement: Continuation link promoted on incomplete answers

When the answer is incomplete and a continuation link exists, that link SHALL be surfaced with top priority (first, or in a dedicated continuation position) rather than buried among speculative drilldowns, consistent with the retrieval-completeness invariant.

#### Scenario: Reviews continuation ranked first

- **WHEN** a product page cannot answer a reviews question but links the reviews page
- **THEN** the reviews link is the top-priority `try_url` entry
