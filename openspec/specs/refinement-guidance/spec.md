# refinement-guidance Specification

## Purpose
TBD - created by archiving change content-aware-refinement-guidance. Update Purpose after archive.
## Requirements
### Requirement: Deterministic context bundle carries no interpretation

The system SHALL assemble a **context bundle** of facts it can know without understanding any
site or language: the requested URL with its query string parsed into opaque `key=value` pairs
(parsed but **not** interpreted — no param is decoded as a "sort" or "filter"), the already-computed
content kind, and the `items_loaded` / `items_total` counts. The bundle SHALL be assembled purely
and non-raising, with zero per-site or per-language knowledge, so that all *interpretation* of the
bundle is left to the reasoning model (server-side on `ask`, or the caller's model on `fetch_raw`).

#### Scenario: Query params are surfaced verbatim, uninterpreted

- **WHEN** a fetch is requested for a URL carrying `?q=ez+rj45&siralama=artanFiyat`
- **THEN** the context bundle exposes `q` and `siralama` as opaque key/value pairs
- **AND** the system does NOT label `siralama=artanFiyat` as a sort, a price order, or any other meaning

#### Scenario: Bundle assembly never raises

- **WHEN** a URL has a malformed or empty query string
- **THEN** the context bundle degrades to the URL with no params rather than raising

### Requirement: Content-type guidance is keyed off closed content-kind enums, never sites

The system SHALL select guidance about what matters for the page in hand from a fixed table
keyed on the existing closed content-kind enums (`structural_form` / `shape` / `genre`), never on
a host or URL. A `listing` kind SHALL steer toward completeness, sort/selection bias, and
refinement axes; a `discussion` kind toward consensus-versus-dissent and recency; an `article`
kind toward claims, recency, and author stance; a `product` kind toward price, specs, and
availability. On the `ask` path the selected guidance SHALL be composed into the server-side
extraction prompt. The guidance table SHALL contain no site, host, or domain string.

#### Scenario: Listing kind selects listing guidance

- **WHEN** a fetched page is classified as a `listing`
- **THEN** the composed guidance covers completeness, selection/sort bias, and refinement axes

#### Scenario: Guidance is site-agnostic

- **WHEN** the guidance table is inspected
- **THEN** no entry references a host, domain, or site name — entries key only on the content-kind enums

#### Scenario: Static MCP tool description is unchanged

- **WHEN** the MCP server advertises tools via `list_tools`
- **THEN** the advertised tool descriptions are identical regardless of any fetched page's kind (the guidance is per-fetch, not part of the static schema)

### Requirement: Refinement axes on a partial listing are dimensional, never values

On a partial listing (per `listing-completeness`), the `ask` path SHALL reason over the content
in hand plus the context bundle and MAY propose **refinement axes** — dimensions to re-query on
(for example: add a price floor, sort by rating, narrow by brand, split by sub-type). Each axis
SHALL name a dimension and how to apply it. The system SHALL NOT emit specific item values drawn
from the retrieved sample as recommendations (for example a specific brand or "the cheapest ones
are best"), because the retrieved sample may be biased by the site's ordering and any value it
names would inherit that bias. Axes SHALL be parsed through the existing wobble funnel and omitted
from the wire when absent.

#### Scenario: Sorted, truncated sample yields axes, not values

- **WHEN** an `ask` fetch returns a partial listing whose retrieved items are the cheapest of a larger, price-sorted result set
- **THEN** the refinement axes name dimensions to re-query on (e.g. "add a price floor", "sort by rating")
- **AND** the axes do NOT recommend a specific brand or item drawn from the retrieved sample

#### Scenario: Complete listing emits no axes

- **WHEN** an `ask` fetch returns a complete listing (no `listing_partial` / `listing_more` signal)
- **THEN** no refinement axes are emitted and the field is absent from the wire

#### Scenario: Non-listing page emits no axes

- **WHEN** an `ask` fetch returns an article or single entity (no `RecordSet`)
- **THEN** no refinement axes are considered or emitted

