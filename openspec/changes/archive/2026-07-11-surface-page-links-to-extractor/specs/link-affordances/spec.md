## ADDED Requirements

### Requirement: Link digest assembled from the page's anchor links

The system SHALL assemble a **link digest** fed to the extractor from the role-classified selectolax `links[]` pass produced by `content_extract` (already flowing to `fc.links`), covering in-body, nav, footer, and tab anchors. This requires no shelf change.

> **Deferred enhancement (separate shelf EVOLVE):** when `trafilatura(include_links=True)` in-body markdown links become available, the digest SHALL additionally union them by target URL (set-difference against the selectolax hrefs) so in-body links retain surrounding-prose position. Additive; not required for v1.

The digest SHALL be assembled only for pages classified `structural_form ∈ {product, listing}`; other genres SHALL NOT incur the digest cost.

#### Scenario: Chrome-only reviews link is surfaced

- **WHEN** a product page links its reviews page only from a footer/tab anchor (absent from in-body prose)
- **THEN** the reviews href appears in the digest via the selectolax set-difference source

#### Scenario: In-body link is surfaced

- **WHEN** a product page body contains `<p>see the <a href="…-yorumlari">reviews</a> before buying</p>`
- **THEN** the digest carries that link (surrounding-prose positional grounding is added by the deferred in-body EVOLVE, not required for v1)

#### Scenario: Article page pays no digest cost

- **WHEN** a page is classified `structural_form: "article"`
- **THEN** no link digest is assembled or fed to the extractor

### Requirement: Placeholder handle encoding

Each link in the digest SHALL be encoded as a numeric, delimited placeholder handle of the form `{{n}}` (n a positive integer), followed by its anchor label and a trimmed path. The domain SHALL be shown only when it differs from the fetched page's domain. Handles SHALL NOT use bare-letter forms (e.g. `L1`) or markdown-bracket forms (e.g. `[L1]`). The extractor SHALL be instructed to emit handles verbatim and never to emit a raw URL.

#### Scenario: Same-domain link omits domain

- **WHEN** a digest link is same-domain as the fetched page
- **THEN** its encoded line shows `{{n}} <label> · <path>` with no domain

#### Scenario: Off-domain link shows domain

- **WHEN** a digest link points to a different domain
- **THEN** its encoded line includes the target domain

### Requirement: Closed-set rehydration

The system SHALL rehydrate emitted handles to real hrefs via a closed-set table built from the digest. A handle not present in the table SHALL be dropped, never emitted to the caller. Rehydration SHALL match only the exact `{{n}}` delimiter form, so that identifier-like substrings inside product names or SKUs (e.g. "Xiaomi L1", "WH-L7", "HBCV0000ATJ8M2") are never altered.

#### Scenario: Unknown handle dropped

- **WHEN** the extractor emits `{{9}}` but the digest has no handle 9
- **THEN** that entry is dropped and does not appear in the response

#### Scenario: Product name not corrupted

- **WHEN** the answer text contains a product named "Xiaomi L1 Desk Lamp" and a handle `{{2}}`
- **THEN** rehydration replaces only `{{2}}` and leaves "Xiaomi L1" unchanged

### Requirement: Safe deterministic cuts only

Before encoding, the system SHALL remove only links that are provably the same document or unfetchable: self-links, fragment-only links (`url#…`), trailing-slash/normalization duplicates, `javascript:` links, and exact-duplicate hrefs. The system SHALL NOT apply relevance-based filtering; all relevance judgment SHALL be performed by the extractor.

#### Scenario: Fragment tab dropped, distinct reviews link kept

- **WHEN** a page has both an inline `#reviews` fragment anchor and a distinct `…-yorumlari` URL
- **THEN** the fragment anchor is dropped and the distinct URL is retained in the digest

#### Scenario: No relevance filtering

- **WHEN** a page yields ~200 candidate links after safe cuts
- **THEN** all remaining links are encoded and fed to the extractor (not pre-filtered to a "relevant" subset)

### Requirement: Contact links retained with value

The system SHALL retain `mailto:` and `tel:` links regardless of DOM role and SHALL surface their raw href value (not placeholdered). When such a link has no anchor text, the system SHALL derive a label from the href.

#### Scenario: Footer email retained

- **WHEN** a page has only `<footer><a href="mailto:support@x.com">E-posta</a></footer>`
- **THEN** the response can report `support@x.com`

#### Scenario: Label-less phone retained

- **WHEN** a page has `<a href="tel:+900000"></a>` with empty anchor text
- **THEN** the link is retained with a label derived from the href

### Requirement: Dedup by target with label union

When one target URL is reached by multiple distinct anchor labels, the system SHALL collapse them to a single handle whose label is the union of the distinct labels.

#### Scenario: Multiple labels merged

- **WHEN** the same product URL is anchored as "Gillette Proglide" and "En çok satan"
- **THEN** one handle is emitted with both labels unioned

### Requirement: Suggestions are neutral affordances, never rankings

Suggested links SHALL present categories of what exists, never a system-chosen "best." For a question that asks the system to pick from a set, the answer SHALL present the option space and MAY offer only a criterion-disclosed lead (e.g. "by rating, X leads"); it SHALL NOT assert the system's own preference.

#### Scenario: "Which is best" does not crown

- **WHEN** asked "which product is best?" on a listing
- **THEN** the answer returns the items with disclosed metadata and, at most, a criterion-disclosed lead — never an unqualified "best" of the system's own

### Requirement: Continuation links are answer material

When the asked question is NOT answered by the current page and a link to the answer exists in the digest, that continuation link SHALL be surfaced with top priority as part of completing the answer (per the retrieval-completeness invariant), not merely as an optional suggestion.

#### Scenario: Reviews-elsewhere returns the reviews link

- **WHEN** a product page is asked to summarize reviews and reviews live at a separate linked URL
- **THEN** that URL is surfaced as a top-priority continuation, rehydrated from a real anchor

### Requirement: Off-domain suggestions are flagged

Rehydrated suggestion targets that point off the fetched page's domain SHALL carry an explicit off-domain flag on the wire, and SHALL require a question-conditioned justification (not a genre justification).

#### Scenario: Off-domain target flagged

- **WHEN** a surfaced suggestion points to a different registrable domain
- **THEN** the wire entry marks it off-domain

### Requirement: Absence is question-scoped, never genre-asserted

When the answer is not on the page and no continuation link is found, the system SHALL report evidence-scoped absence ("asked-for content not on this page; no link to it found in the extracted set") and SHALL NOT assert genre-level nonexistence ("products usually have reviews; none exist").

#### Scenario: Honest miss without false nonexistence

- **WHEN** reviews are neither on the page nor linked in the extracted set
- **THEN** the response states the content and its link were not found, without claiming reviews do not exist
