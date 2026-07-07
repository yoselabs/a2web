## MODIFIED Requirements

### Requirement: JSON-LD Product / Article shapes have preferred status

When multiple payloads are present, downstream consumers SHALL prefer them in this bucket order, descending:

0. `ld_json` (strong: `Product`, `Article`, `ItemList`, `BreadcrumbList`, `NewsArticle`, `LocalBusiness`, `Organization`, `ContactPoint`, `Event`, `Recipe` with ≥3 populated fields)
1. `microdata` (strong: same `@type` set as ld_json strong, ≥3 populated fields)
2. `next_data`, `nuxt_data`
3. `opengraph`
4. `ld_json` (weak), `microdata` (weak)
5. `window_var`
6. `generic`

Within each bucket, larger payloads (`byte_size` descending) rank first. The ranking SHALL be implemented as a pure function `rank_payloads(payloads: list[JsonPayload]) -> list[JsonPayload]` so callers can override.

The strong `@type` set (`_PREFERRED_LD_TYPES`) SHALL cover both the commerce/editorial types (`Product`, `Article`, `NewsArticle`, `ItemList`, `BreadcrumbList`) AND the entity/answer types (`LocalBusiness`, `Organization`, `ContactPoint`, `Event`, `Recipe`). The `≥3 populated fields beyond @type` threshold is unchanged, so a stub entity (e.g. a `LocalBusiness` with only `name` + `url`) remains weak. `@type` matching SHALL continue to accept a single string or a list of strings, and a `LocalBusiness` subtype string (e.g. `Store`, `Restaurant`) that appears in the set matches directly.

#### Scenario: Product LD-JSON wins over Next.js pageProps

- **WHEN** a page has both `__NEXT_DATA__` (with pageProps) and JSON-LD `Product` schema with name/price/aggregateRating
- **THEN** `rank_payloads` returns the LD-JSON payload first

#### Scenario: Empty LD-JSON loses to populated Next.js payload

- **WHEN** a page has both, but the LD-JSON `Product` has only `@type` and `name` (2 fields, below threshold)
- **THEN** `rank_payloads` returns the `next_data` payload first

#### Scenario: Strong microdata beats next_data

- **WHEN** a page has both `next_data` (with arbitrary pageProps) and strong microdata `Product` (≥3 fields)
- **THEN** `rank_payloads` returns the microdata payload first (bucket 1 vs bucket 2)

#### Scenario: OpenGraph ranks behind framework app-state

- **WHEN** a page has both `next_data` and `opengraph`
- **THEN** `rank_payloads` returns the `next_data` payload first

#### Scenario: Strong LocalBusiness ld_json ranks in bucket 0

- **WHEN** a page carries a `LocalBusiness` JSON-LD with `name`, `telephone`, `email`, `url`, `image` (5 populated fields) alongside an `opengraph` payload
- **THEN** `rank_payloads` returns the `LocalBusiness` ld_json first (bucket 0, ahead of opengraph in bucket 3)

#### Scenario: Weak Organization ld_json ranks in bucket 4

- **WHEN** a page carries an `Organization` JSON-LD with only `name` + `url` (2 fields, below threshold)
- **THEN** it ranks in bucket 4 (`ld_json` weak), behind framework app-state and opengraph

## ADDED Requirements

### Requirement: is_answer_bearing predicate marks strong structured payloads

The `json_in_script` package SHALL expose a pure predicate
`is_answer_bearing(payload: JsonPayload) -> bool` that returns `True` when the
payload is a **strong** `ld_json` or **strong** `microdata` payload — i.e. an
`@type` in the strong set (`_PREFERRED_LD_TYPES`) with ≥3 populated fields beyond
`@type`, per the same `_ld_json_strong` / `_microdata_strong` predicates used by
`rank_payloads` bucketing. All other sources (`next_data`, `nuxt_data`,
`opengraph`, `window_var`, `generic`, and weak `ld_json` / `microdata`) SHALL
return `False`.

The predicate is the package-owned definition of "this payload carries an answer,
not just page chrome." Consumers (the extraction ladder tagging
`ContentCandidate.answer_bearing`, and thereby the quality-gate exemption) SHALL
use it rather than re-deriving schema strength, so schema knowledge stays inside
the package and out of the gate seam.

#### Scenario: Strong Product payload is answer-bearing

- **WHEN** `is_answer_bearing` is called on an `ld_json` payload holding a `Product` with `name`, `offers`, `aggregateRating` (≥3 fields)
- **THEN** it returns `True`

#### Scenario: Strong LocalBusiness payload is answer-bearing

- **WHEN** `is_answer_bearing` is called on an `ld_json` payload holding a `LocalBusiness` with `name`, `telephone`, `email` (≥3 fields)
- **THEN** it returns `True`

#### Scenario: Weak entity payload is not answer-bearing

- **WHEN** `is_answer_bearing` is called on an `ld_json` `Organization` with only `name` + `url` (2 fields)
- **THEN** it returns `False`

#### Scenario: OpenGraph and framework state are not answer-bearing

- **WHEN** `is_answer_bearing` is called on an `opengraph` payload, or on a `next_data` payload
- **THEN** it returns `False` (these rank behind strong structured data and do not, on their own, exempt a page from the length floor)
