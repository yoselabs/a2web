# record-extraction Specification

## Purpose

trafilatura is an article extractor — it discards repeated DOM structure as boilerplate, so listing / index pages are gutted. `record-extraction` recovers them: locate the dominant repeated record region in server-rendered HTML, render that bounded subtree to link-preserving markdown, and expose each record so the domain seam can populate `next_links`. It is the structural-record rung of the extraction-escalation ladder.
## Requirements
### Requirement: Locate the dominant repeated record region

The `record_extract` package SHALL provide a function that takes listing / index / discussion HTML and returns the dominant repeated record region. Detection SHALL be **tree-aware**: the function counts each `(tag, first-class-token)` signature **document-wide** — not only among the direct children of one container — so that a recursively nested record region (a threaded comment tree) is located as well as a flat sibling list. The occurrences of the chosen signature are the records, rooted at their lowest common ancestor. A record is content-bearing when its **own scope** carries substantive text AND at least one link — own scope excludes text and links inside nested child-records of the same signature, so an outer record is not credited with its children's content.

The function SHALL reject a candidate signature unless all of these guards hold:

- **(a) non-empty class token** — the signature's class component is not empty (document structure such as bare `<section>` / `<p>` is excluded; genuine records carry a semantic class).
- **(b) parent-signature consistency ≥ 0.70** — the records share one dominant parent signature (scattered page chrome does not).
- **(c) heading-presence ≥ 0.50** — at least half the records contain a heading element (`h1`–`h6` or `[role=heading]`).

When multiple signatures clear the guards, the function SHALL rank them by record count weighted by per-record own-scope text volume, and SHALL break a near-tie in favour of the outer signature — the candidate whose signature is a parent-signature of another tied candidate.

#### Scenario: Flat sibling list is located

- **WHEN** the function is given a flat listing page — a container of many repeated content-bearing record elements
- **THEN** the returned region is that list, with all records at depth 0

#### Scenario: Nested comment tree is located

- **WHEN** the function is given a threaded discussion page whose comment elements nest recursively inside one another
- **THEN** the returned region is the comment tree, with records carrying their nesting depth

#### Scenario: Reference-doc sections are rejected

- **WHEN** the function is given a reference-doc page whose repeated heading-bearing `<section>` elements have an empty class
- **THEN** the non-empty-class guard rejects the signature and the function returns no region

#### Scenario: Scattered chrome is rejected

- **WHEN** a repeated signature's occurrences do not share a dominant parent signature (consistency below 0.70)
- **THEN** that signature is rejected as page chrome

#### Scenario: Article prose paragraphs are rejected

- **WHEN** a repeated signature's records mostly lack a heading element (heading-presence below 0.50)
- **THEN** that signature is rejected

### Requirement: Render the record region to link-preserving markdown

The package SHALL render a located record region to markdown that preserves every link — anchor text and href — within each record. It SHALL NOT select a single "primary" link per record for the rendered markdown: all links are retained for a downstream consumer to choose from. Rendering SHALL be **depth-aware** — a flat record set renders as a flat list; a threaded record set renders with indentation reflecting the nesting depth of each record. Each record's rendered text and links SHALL be its **own scope**: the text and links of a nested child-record SHALL NOT be duplicated into its parent. Rendering SHALL operate on the bounded region subtree only, never the whole page.

#### Scenario: Flat catalog renders as a flat list

- **WHEN** a flat (depth 0) record set is rendered
- **THEN** each record is a list entry carrying its slug text and every link in that record

#### Scenario: Threaded discussion renders with depth

- **WHEN** a threaded (depth > 0) record set is rendered
- **THEN** each record is indented by its nesting depth, and no record's text is duplicated into its parent

### Requirement: Record extraction emits next_links candidates

A **flat** record set (depth 0) SHALL emit `next_links` candidates; each record SHALL emit up to two: a **source** candidate carrying the record's heading link (the discussed page) and a **discussion** candidate carrying a same-host permalink to the discussion when one is present — identified generically by an anchor matching a comment-count pattern (e.g. `"N comments"`) or a thread-permalink path. Candidates SHALL be deduplicated by URL, and archive-mirror hosts SHALL be skipped. A **threaded** record set (depth > 0) SHALL NOT emit `next_links` — its records are a conversation already inline on the page, not drilldown targets. The domain seam converts candidates into `NextLink` values, carrying the corresponding `kind` (`source` or `discussion`).

#### Scenario: Aggregator record emits both destinations

- **WHEN** a flat listing record carries both an external article link and an `"N comments"` discussion link
- **THEN** it emits one `source` candidate and one `discussion` candidate

#### Scenario: Record with only a source link emits one candidate

- **WHEN** a flat listing record carries a heading link but no discussion link
- **THEN** it emits a single `source` candidate

#### Scenario: Threaded record set emits no next_links

- **WHEN** the detected region is a threaded (depth > 0) discussion
- **THEN** no `next_links` candidates are emitted

### Requirement: No dominant region yields a clean empty result

When no repeated region clears the content-bearing floor — an article, a near-empty JS shell, a blocked page — the function SHALL return an explicit "no region" result, never a partial or speculative region. The escalation ladder treats this as "fall through to the next source."

#### Scenario: Single article returns no region

- **WHEN** the function is given a single-article page
- **THEN** it returns the no-region result and no records

#### Scenario: Near-empty shell returns no region

- **WHEN** the function is given a near-empty HTML shell (a JS app mount point with no server-rendered records)
- **THEN** it returns the no-region result and no records — no speculative region is emitted

### Requirement: Package independence

The `record_extract` package SHALL live under `src/a2web/packages/` and SHALL NOT import from any `a2web.<domain>` module. Boundary types (record and record-set dataclasses) are package-owned; the domain seam owns conversion to `content_md` and `NextLink`.

#### Scenario: Static import check passes

- **WHEN** `tests/test_packages_independence.py` walks every `.py` under `packages/`
- **THEN** `record_extract` contributes zero imports from `a2web.<domain>`

