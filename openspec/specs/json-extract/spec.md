# json-extract Specification

## Purpose
TBD - created by archiving change harsh-test-session-fixes. Update Purpose after archive.
## Requirements
### Requirement: Detect known JSON-in-script payload shapes

The `json_in_script` extractor SHALL scan response HTML for the following structured-data sources and emit a typed `JsonPayload` record for each match it can parse:

Script-tag-based sources (scanned via selectolax):
- `<script id="__NEXT_DATA__" type="application/json">` → `source="next_data"`
- `<script id="__NUXT_DATA__">` → `source="nuxt_data"`
- `<script type="application/ld+json">` → `source="ld_json"`
- `<script type="application/json"[data-*]>` (Yandex-style generic app-state) → `source="generic"`
- `window.<name> = {...}` JavaScript assignments inside `text/javascript` script blocks for the conservative `_WINDOW_VAR_NAMES` set (`state`, `__INITIAL_STATE__`, `__PRELOADED_STATE__`, `__APP_DATA__`, `__APP_STATE__`, `__DATA__`, `__REDUX_STATE__`, `__SSR__`, `__APOLLO_STATE__`, `__NUXT__`) → `source="window_var"`

Attribute-based sources (scanned via the selectolax DOM tree, no third-party library):
- HTML5 microdata (`itemscope` / `itemprop` / `itemtype`) → `source="microdata"`
- OpenGraph (`<meta property="og:*">` and `article:*` / `product:*` / `book:*` / `profile:*` namespaces) → `source="opengraph"`

RDFa is intentionally out of scope (see this change's `design.md` D1 for the
mid-implementation inversion away from extruct). A dedicated path can be
added later if a real RDFa-shaped failure surfaces.

`JsonPayload` is a package-owned `@dataclass(slots=True, frozen=True)` with fields:

- `source: Literal["next_data","nuxt_data","ld_json","generic","window_var","microdata","opengraph"]`
- `data: dict | list`
- `script_id: str | None` (the matched tag's `id` attribute for script-tag sources; the window var name for `window_var`; `None` for attribute-based payloads)
- `byte_size: int` (length of the source JSON text for script-tag sources; for attribute-based payloads, the byte length of `json.dumps(data)`)

Parse failures SHALL be silently skipped — the extractor returns a partial list, never raises on malformed JSON. The microdata + OpenGraph walks SHALL stay inside `extract_json_payloads` so the existing `asyncio.to_thread` wrap at the orchestrator's `_phase_extract` call site covers them.

#### Scenario: Next.js page yields __NEXT_DATA__ payload

- **WHEN** the extractor scans HTML containing `<script id="__NEXT_DATA__" type="application/json">{"pageProps":{"products":[...]}}</script>`
- **THEN** the returned list contains a `JsonPayload(source="next_data", data={"pageProps": ...}, script_id="__NEXT_DATA__", byte_size=<n>)`

#### Scenario: JSON-LD Product schema is detected

- **WHEN** the extractor scans HTML with a `<script type="application/ld+json">` block containing a `Product` with `offers` and `aggregateRating`
- **THEN** a payload with `source="ld_json"` and the parsed dict is returned

#### Scenario: Microdata Product is detected

- **WHEN** the extractor scans an HTML page bearing `itemscope itemtype="https://schema.org/Product"` with `itemprop="name"`, `itemprop="offers"` (nested), and `itemprop="aggregateRating"` (nested)
- **THEN** the returned list contains a `JsonPayload(source="microdata", data={...flattened product dict...}, script_id=None, byte_size=<n>)`

#### Scenario: OpenGraph meta tags are detected

- **WHEN** the extractor scans an HTML page with `<meta property="og:title" content="...">` and `<meta property="og:type" content="product">` and `<meta property="og:price:amount" content="49.99">`
- **THEN** the returned list contains a `JsonPayload(source="opengraph", data={...og keys...}, script_id=None, byte_size=<n>)`

#### Scenario: Page with neither script-tag nor extruct-discoverable data returns empty list

- **WHEN** the extractor scans an HTML page with no recognized script-tag patterns and no microdata / RDFa / OG attributes
- **THEN** the returned list is empty

#### Scenario: Malformed JSON does not raise

- **WHEN** the extractor encounters a `<script>` with a matching selector but a JSON body that fails to parse (e.g., a JS expression, not pure JSON)
- **THEN** that script tag is silently skipped; other matching tags on the page are still emitted

### Requirement: JSON-LD Product / Article shapes have preferred status

When multiple payloads are present, downstream consumers SHALL prefer them in this bucket order, descending:

0. `ld_json` (strong: `Product`, `Article`, `ItemList`, `BreadcrumbList`, `NewsArticle` with ≥3 populated fields)
1. `microdata` (strong: same `@type` set as ld_json strong, ≥3 populated fields)
2. `next_data`, `nuxt_data`
3. `opengraph`
4. `ld_json` (weak), `microdata` (weak)
5. `window_var`
6. `generic`

Within each bucket, larger payloads (`byte_size` descending) rank first. The ranking SHALL be implemented as a pure function `rank_payloads(payloads: list[JsonPayload]) -> list[JsonPayload]` so callers can override.

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

### Requirement: Package independence preserved

The `json_in_script` module SHALL live under `src/a2web/packages/`. It SHALL NOT import from any `a2web.<domain>` module. Boundary types (`JsonPayload`, `JsonSource`) are package-owned. Only the existing third-party imports (selectolax) are used; no library beyond what's already in the dep tree. The existing `tests/test_packages_independence.py` invariant continues to apply.

#### Scenario: Static import check passes

- **WHEN** `tests/test_packages_independence.py` walks every `.py` under `packages/`
- **THEN** zero imports from `a2web.<domain>` are found in `packages/json_in_script.py`; selectolax remains the only third-party HTML dependency

### Requirement: Detect a whole-response JSON body

The `json_in_script` extractor SHALL provide `parse_json_response(text: str) -> JsonPayload | None` that parses an entire response body as a single top-level JSON document and returns a `JsonPayload(source="generic", data=<parsed>, script_id=None, byte_size=<len(text)>)`. On any parse failure it SHALL return `None` (never raise), so the orchestrator can fall back to normal handling.

This function SHALL own `json.loads` for the response-body path (as `extract_json_payloads` already owns it for the in-script path), keeping the architecture's json-loads funnel invariant intact — no `json.loads` call is added outside the `json_in_script` package.

The emitted `source="generic"` payload SHALL route through the existing `json_to_markdown_rows` synthesis (which already handles `generic`), so a top-level `{"products": [...]}`, `{"items": [...]}`, or bare array of objects renders to markdown with no new domain code.

#### Scenario: A JSON object response parses to a generic payload

- **WHEN** `parse_json_response('{"products": [{"name": "Widget", "price": "9.99"}]}')` is called
- **THEN** it returns a `JsonPayload(source="generic", data={"products": [...]}, script_id=None, byte_size=<n>)`

#### Scenario: A JSON array response parses to a generic payload

- **WHEN** `parse_json_response('[{"title": "A"}, {"title": "B"}]')` is called
- **THEN** it returns a `JsonPayload(source="generic", data=[...], script_id=None)`

#### Scenario: A non-JSON body returns None

- **WHEN** `parse_json_response('<html>not json</html>')` is called
- **THEN** it returns `None` (no raise)

#### Scenario: A truncated / malformed JSON body returns None

- **WHEN** `parse_json_response('{"a": 1,')` is called
- **THEN** it returns `None` (no raise)

