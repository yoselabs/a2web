# record-extraction Specification

## Purpose

trafilatura is an article extractor — it discards repeated DOM structure as boilerplate, so listing / index pages are gutted. `record-extraction` recovers them: locate the dominant repeated record region in server-rendered HTML, render that bounded subtree to link-preserving markdown, and expose each record so the domain seam can populate `next_links`. It is the structural-record rung of the extraction-escalation ladder.

## Requirements

### Requirement: Locate the dominant repeated record region

The `record_extract` package SHALL provide a function that takes parsed listing / index HTML and returns the dominant repeated record region — the container element whose direct children include the largest set of content-bearing repeats of one structural signature, where a content-bearing child carries substantive text AND at least one link. When multiple repeated regions exist, the function SHALL rank them by record count weighted by per-record text volume, so that page chrome (navigation menus, footers, sidebar link lists) ranks below genuine record clusters.

#### Scenario: Repo-card cluster beats marketing navigation

- **WHEN** the function is given GitHub-trending-shaped HTML containing a repeated `<article>` repo-card cluster and a marketing-navigation `<ul>`
- **THEN** the returned region is the repo-card cluster, not the navigation list

#### Scenario: Flat link list is located

- **WHEN** the function is given a flat list page — a `<ul>` of many link items
- **THEN** the returned region is that list

#### Scenario: Article page yields no region

- **WHEN** the function is given an article page whose only repeated structures are small chrome blocks below the content-bearing floor
- **THEN** the function returns no region

### Requirement: Render the record region to link-preserving markdown

The package SHALL render a located record region to markdown that preserves every link — anchor text and href — within each record. It SHALL NOT select a single "primary" link per record: the first link in a record is frequently chrome (an action button), so all links are retained for a downstream consumer to choose from. Rendering SHALL operate on the bounded region subtree only, never the whole page.

#### Scenario: Each record keeps its slug text and all links

- **WHEN** a repo-card region is rendered
- **THEN** each record's markdown contains the repo slug text and every link present in that card

#### Scenario: Action link and content link both retained

- **WHEN** a record contains a leading action link followed by the content link
- **THEN** both links appear in the rendered markdown for that record

### Requirement: Record extraction emits next_links candidates

Each detected record SHALL also be emitted as a structured candidate carrying the record's most prominent link (its heading link — not link index 0), its anchor text, and a short reason. The domain seam converts these candidates into `NextLink` values, populating `next_links` for listing pages that have no site handler.

#### Scenario: Un-handled listing page gets next_links

- **WHEN** a listing page with no matching site handler is record-extracted
- **THEN** the result carries one candidate per detected record, each pointing at the record's prominent link

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
