## ADDED Requirements

### Requirement: A partial listing is never mistakable for a complete one

The response SHALL carry an honest partial signal — a `listing_partial` operator
hint plus `items_loaded` / `items_total` fields — whenever a fetched listing (the
generic record extractor produced a `RecordSet`) has a parsed record count that
falls short of an authoritative item oracle within tolerance, so the caller
cannot mistake a truncated sample for the whole listing. This is the
never-silently-miss floor (ADR-0009) applied on the sufficiency axis: a page can
render cleanly, pass every gate, and carry real records yet still be partial
because infinite-scroll / lazy-load only materialised the first batch.

The signal is informational, not a wall: a partial listing returned real,
usable records, so it SHALL NOT set `retrieval_incomplete` or `status: failed`
(those remain reserved for zero-useful-content walls and obstacles). The floor is
satisfied by loudness, not by a failed status.

#### Scenario: Short-of-oracle listing surfaces a partial signal

- **WHEN** a fetch parses 31 records and an item oracle of 40 is extracted from the page
- **THEN** the response carries a `listing_partial` info hint with `items_loaded: 31` and `items_total: 40`
- **AND** the response does NOT set `retrieval_incomplete` or `status: failed`

#### Scenario: Complete listing emits nothing

- **WHEN** the parsed record count meets or exceeds the oracle within tolerance
- **THEN** no `listing_partial` hint is emitted and the `items_loaded` / `items_total` fields are absent from the wire

#### Scenario: Non-listing page carries no listing fields

- **WHEN** a fetched page produces no `RecordSet` (an article, a single entity)
- **THEN** the `items_loaded` / `items_total` fields are absent and no partial signal is considered

### Requirement: Generic item-count oracle

The item oracle SHALL be extracted generically — with no per-host handler — in
reliability order: a structured `ItemList.numberOfItems` (JSON-LD / microdata)
first, then an anchored visible-count match (result/product/item nouns, e.g.
"40 sonuç", "1,234 results", "showing 1–24 of 40"), else `None`. Oracle
extraction SHALL be pure and non-raising: any failure yields `None` and the page
is treated as having no numeric oracle. When no numeric oracle exists but a
structural "more exists" indicator is present (a `rel=next` link, a load-more
control, or pagination navigation) on a non-scrolling tier, the response MAY
carry a countless `listing_partial` signal ("more items available") without a
fabricated total.

#### Scenario: Structured count wins

- **WHEN** a listing page carries both a JSON-LD `ItemList.numberOfItems` of 40 and a visible "about 40 results" string
- **THEN** the oracle is taken from the structured `numberOfItems`

#### Scenario: Visible count when unstructured

- **WHEN** a listing page carries no structured item count but shows "40 sonuç"
- **THEN** the oracle is 40 from the anchored visible-count match

#### Scenario: No oracle, structural signal only

- **WHEN** no numeric oracle is extractable but the page carries a `rel=next` / load-more control and was served by a non-scrolling tier
- **THEN** a countless `listing_partial` signal ("more items available") is emitted with no `items_total`

### Requirement: Sufficiency verdict reuses the content-expectations contract

The partial-vs-complete decision SHALL be resolved by
`content_expectations.assess(loaded, total)` — the same oracle-vs-progress
contract used for Reddit comment completeness — with `loaded` the parsed record
count and `total` the item oracle. A positive oracle with zero parsed records is
the presence axis, not the sufficiency axis: it SHALL defer to the existing
obstacle / wall machinery rather than emit a duplicate partial signal.

#### Scenario: Assess drives the verdict

- **WHEN** `loaded` records fall below `total · tolerance`
- **THEN** `assess` returns `partial` and the `listing_partial` signal fires

#### Scenario: Positive oracle, zero records defers to presence axis

- **WHEN** the oracle is positive but zero records parsed (`assess` → `fail`)
- **THEN** no `listing_partial` signal is emitted and the existing obstacle / wall path owns the miss

### Requirement: Shape-aware completion steer

The `listing_partial` signal SHALL steer the caller toward the correct
completion for the page shape, reusing the existing `try_url` / `ask_here`
envelope fields. For a search-shaped URL the steer SHALL advise narrowing the
query (the correct completion of a too-broad result set); for a bounded list it
SHALL advise scrolling / opening in a browser.

#### Scenario: Search listing steers toward a narrower query

- **WHEN** a partial listing is served from a search-shaped URL (`?q=` / `/ara` / `/search`)
- **THEN** the response adds a narrow-the-query `try_url` / `ask_here` steer rather than advising pagination

#### Scenario: Bounded list steers toward scroll

- **WHEN** a partial listing has a small known oracle and is not search-shaped
- **THEN** the steer advises scrolling / opening the page in a browser

### Requirement: Bounded scroll-to-complete or steer, never unbounded

Listing completion, when enabled, SHALL close a `listing_partial` verdict on a
non-scrolling tier by a bounded scrolling render OR a narrow-the-query steer,
chosen by the oracle: a small/bounded oracle scrolls; an oracle above the
completion ceiling (`SCROLL_MAX`, a broad search) steers without scrolling. The
scrolling render SHALL terminate when the record count stops growing across a
scroll step OR a scroll cap / time budget is reached — no oracle is required to
terminate. After a scrolling render the listing SHALL be re-counted
and re-assessed: reaching the oracle / stabilising drops the signal; a capped,
virtualised, or still-short result keeps `listing_partial` (the miss stays loud).

#### Scenario: Bounded listing scrolls to completion

- **WHEN** completion is enabled, the oracle is 40 (≤ `SCROLL_MAX`), and the initial render carries 31 records
- **THEN** the render scrolls until the count stabilises or the cap is hit, re-counts, and — reaching 40 — returns complete with no `listing_partial` signal

#### Scenario: Broad search steers instead of scrolling

- **WHEN** the oracle exceeds `SCROLL_MAX` (a search with thousands of hits)
- **THEN** no scroll is attempted and the response carries the `listing_partial` signal plus a narrow-the-query steer

#### Scenario: Virtualised listing keeps the signal after scrolling

- **WHEN** a scrolling render cannot accumulate the count (rows unmount on scroll) and stops short of the oracle
- **THEN** the response keeps the `listing_partial` signal (scroll cannot beat virtualisation and says so)

### Requirement: Listing completion shares the single paid-dispatch cap

A `listing_partial` scrolling render SHALL reuse the `escalate_to_render` /
`_escalate_paid` path and share the single one-paid-dispatch-per-fetch budget
with the gate-wall and obstacle render triggers. At most one render occurs per
fetch regardless of how many triggers fire; a fetch that already spent its
render does not get a second one for the listing — the signal simply stands. The
free own-browser (with scroll) SHALL be preferred before paid egress where
available.

#### Scenario: Shared cap blocks a second render

- **WHEN** a fetch already spent its paid render on a gate wall or an obstacle and then produces a `listing_partial` verdict
- **THEN** no second render is dispatched and the `listing_partial` signal stands

#### Scenario: Own-browser preferred over paid egress

- **WHEN** listing completion needs a scrolling render and a free own-browser backend is available
- **THEN** the own-browser scroll is attempted before spending the paid tier
