# json-extract Specification

## Purpose
TBD - created by archiving change harsh-test-session-fixes. Update Purpose after archive.
## Requirements
### Requirement: Detect known JSON-in-script payload shapes

The `json_in_script` extractor SHALL scan response HTML for the following script-tag patterns and emit a typed `JsonPayload` record for each match it can parse as valid JSON:

- `<script id="__NEXT_DATA__" type="application/json">` → `source="next_data"`
- `<script id="__NUXT_DATA__">` → `source="nuxt_data"`
- `<script type="application/ld+json">` → `source="ld_json"`
- `<script type="application/json"[data-*]>` (Yandex-style generic app-state) → `source="generic"`

`JsonPayload` is a package-owned `@dataclass(slots=True)` with fields `source: Literal["next_data","nuxt_data","ld_json","generic"]`, `data: dict | list`, `script_id: str | None`, `byte_size: int`. Parse failures SHALL be silently skipped (the extractor returns a partial list, never raises on malformed JSON).

#### Scenario: Next.js page yields __NEXT_DATA__ payload

- **WHEN** the extractor scans HTML containing `<script id="__NEXT_DATA__" type="application/json">{"pageProps":{"products":[...]}}</script>`
- **THEN** the returned list contains a `JsonPayload(source="next_data", data={"pageProps": ...}, script_id="__NEXT_DATA__", byte_size=<n>)`

#### Scenario: JSON-LD Product schema is detected

- **WHEN** the extractor scans HTML with a `<script type="application/ld+json">` block containing a `Product` with `offers` and `aggregateRating`
- **THEN** a payload with `source="ld_json"` and the parsed dict is returned

#### Scenario: Malformed JSON does not raise

- **WHEN** the extractor encounters a `<script>` with a matching selector but a JSON body that fails to parse (e.g., a JS expression, not pure JSON)
- **THEN** that script tag is silently skipped; other matching tags on the page are still emitted

#### Scenario: Page with no recognized payloads returns empty list

- **WHEN** the extractor scans a plain SSR article page with no recognized JSON-in-script tags
- **THEN** the returned list is empty

### Requirement: JSON-LD Product / Article shapes have preferred status

When both `ld_json` *and* `next_data` payloads are present, downstream consumers SHALL prefer `ld_json` when it contains a recognizable schema (`Product`, `Article`, `ItemList`, `BreadcrumbList`) with ≥3 populated fields. Otherwise, `next_data` is the fallback. The ranking SHALL be implemented as a pure function `rank_payloads(payloads: list[JsonPayload]) -> list[JsonPayload]` so callers can override.

#### Scenario: Product LD-JSON wins over Next.js pageProps

- **WHEN** a page has both `__NEXT_DATA__` (with pageProps) and JSON-LD `Product` schema with name/price/aggregateRating
- **THEN** `rank_payloads` returns the LD-JSON payload first

#### Scenario: Empty LD-JSON loses to populated Next.js payload

- **WHEN** a page has both, but the LD-JSON `Product` has only `@type` and `name` (2 fields, below threshold)
- **THEN** `rank_payloads` returns the `next_data` payload first

### Requirement: Package independence preserved

The `json_in_script` module SHALL live under `src/a2web/packages/content_extract/` (or a sibling package directory). It SHALL NOT import from any `a2web.<domain>` module. Boundary types (`JsonPayload`) are package-owned. The existing `tests/test_packages_independence.py` invariant continues to apply.

#### Scenario: Static import check passes

- **WHEN** `tests/test_packages_independence.py` walks every `.py` under `packages/`
- **THEN** zero imports from `a2web.<domain>` are found in `content_extract/json_in_script.py`

