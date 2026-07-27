## ADDED Requirements

### Requirement: a page's anchors survive retrieval regardless of which tier served it

When a fetch retrieves a page whose body carries anchors, those anchors SHALL be
available to the response pipeline irrespective of which tier won. A tier that
installs pre-rendered markdown SHALL carry the page's links across that seam
rather than dropping them.

Retrieval path is not a property the caller chose or can see. Making the index
depend on it means the same URL yields an index or does not according to whether
an anti-bot wall happened to force a browser — and it fails precisely on the
pages the caller can least afford to re-fetch.

#### Scenario: a link-dense page served by a pre-rendering tier

- **WHEN** a page carrying many anchors is retrieved by a tier that installs
  pre-rendered markdown (browser, archive, or a site handler over HTML)
- **THEN** the page's links are available to the link digest
- **AND** the count is commensurate with the anchors present in the retrieved body

#### Scenario: the same page served by two different tiers

- **WHEN** the same link-dense page is retrieved once by the raw tier and once by
  a pre-rendering tier
- **THEN** both fetches make the page's links available
- **AND** neither yields an empty link set while the other does not

### Requirement: an index-capable page is not silently reported as index-free

An empty link set on a page whose retrieved body contained anchors SHALL be
treated as a defect in retrieval, not as a property of the page. The system SHALL
NOT present an absent index as though the page offered nothing to point at.

#### Scenario: anchors present, links empty

- **WHEN** the retrieved body contains anchors and the extracted link set is empty
- **THEN** this is a failure of the extraction path, not a page with no links

### Requirement: bodies that are not HTML are a known, stated gap

Tiers whose retrieved body is not HTML — a markdown reader's output, or a JSON
API payload — are NOT covered by the requirement above. This SHALL be recorded
as a known gap rather than left implicit, so that a later reader can tell an
unsolved case from an overlooked one.

#### Scenario: a markdown-reader tier

- **WHEN** a tier returns markdown rather than HTML as its body
- **THEN** the anchors-survive-retrieval requirement does not apply to it
- **AND** the gap is documented rather than silently absent
