## MODIFIED Requirements

### Requirement: JSON-LD single-entity rendering is default-keep, not an allowlist

Single-entity JSON-LD rendering (`Product` / `Article` / `NewsArticle` / `Recipe`, plus the entity/answer schemas `LocalBusiness` / `Organization` / `ContactPoint` / `Event`, and the like) SHALL render answer-bearing fields by **default-keep**: every key whose value is a scalar, a shallow dict of scalars, a list of scalars, OR a list of shallow dicts SHALL be surfaced, in the entity's own field order, EXCEPT a fixed **noise denylist** — JSON-LD machinery (`@context`, `@type`, `@id`, `@graph`), image/media URLs (`image`, `thumbnail`, `thumbnailUrl`, `logo`), `mainEntityOfPage`, and values exceeding a length cap (so a full article body is not dumped into a key-value line). The renderer's entity-type dispatch SHALL cover the answer/entity schemas (`LocalBusiness`, `Organization`, `ContactPoint`, `Event`) alongside the commerce/editorial types, so a contact page's `LocalBusiness` renders its `telephone` / `email` / `address` rather than producing an empty string. The renderer SHALL NOT gate fields against a fixed allowlist of "interesting" keys; an answer-bearing field the author did not anticipate (e.g. a `Product.gtin`, a `Recipe.recipeYield`) SHALL still be surfaced. This eliminates the value-blind structural-filter projection (ADR-0003 / ADR-0004).

When a field's value is a **list of dicts** (e.g. `Organization.contactPoint` holding multiple `ContactPoint` entries — a schema.org-valid shape for multiple departments/locations), the renderer SHALL render each dict element as its own flattened sub-line under the parent key (reusing the same one-level scalar flatten already applied to a single nested dict), rather than silently dropping the field. The renderer SHALL cap the number of rendered array entries defensively (a small fixed cap, mirroring the existing per-file caps on unbounded input) to bound prompt growth on pathological pages. This closes the one shape the default-keep philosophy did not originally anticipate: previously, a list containing zero bare scalars (i.e. entirely dicts) rendered to an empty joined string and the whole field vanished with no signal that anything was dropped.

#### Scenario: An unanticipated answer-bearing field is surfaced

- **WHEN** a JSON-LD entity carries a scalar field outside any prior fixed allowlist (e.g. `gtin13`, `recipeYield`)
- **THEN** `json_to_markdown_rows` includes that field's key and value in the rendered entity

#### Scenario: Known noise is dropped

- **WHEN** a JSON-LD entity carries `@type`, `@context`, `image`, and a 5,000-character `articleBody`
- **THEN** the rendered entity omits the `@`-prefixed keys, the image URL, and the oversized body, while keeping the entity's short answer-bearing scalars

#### Scenario: A LocalBusiness entity renders its contact fields

- **WHEN** `json_to_markdown_rows` is given an `ld_json` payload holding a `LocalBusiness` with `name`, `telephone`, `email`, `url`
- **THEN** the rendered markdown is non-empty and contains the `telephone` and `email` values (previously it rendered to an empty string because the type was outside the dispatch allowlist)

#### Scenario: An array of ContactPoint entries renders each entry distinctly

- **WHEN** `json_to_markdown_rows` is given an `Organization` whose `contactPoint` field is a list of two `ContactPoint` dicts — one `{"telephone": "+1-800-555-0100", "contactType": "sales"}`, one `{"telephone": "+1-800-555-0200", "contactType": "support", "email": "support@example.com"}`
- **THEN** the rendered markdown contains both telephone numbers, each associated with its own `contactType`, and the `support@example.com` email — not a single collapsed or empty line

#### Scenario: An array of ContactPoint entries no longer vanishes silently

- **WHEN** the same `contactPoint` array is rendered under the pre-fix behavior (a list-value branch that only keeps bare scalars)
- **THEN** (documenting the fixed defect) the field previously produced an empty joined string and no line was emitted for `contactPoint` at all, despite two populated entries being present

#### Scenario: Scalar lists are unaffected

- **WHEN** a JSON-LD entity carries a list-of-scalars field (e.g. `keywords: ["a", "b", "c"]`)
- **THEN** the rendered line is the existing comma-joined scalar format, unchanged by the list-of-dicts handling

#### Scenario: Oversized entity arrays are capped

- **WHEN** an entity field's array value contains far more dict entries than the defensive cap
- **THEN** the renderer emits only up to the capped number of entries, not the full array
