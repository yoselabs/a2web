## Why

On a product-listing page whose data is fully present in the raw HTML (e.g. Hepsiburada, a JSON-LD `ItemList` of 36 `Product` entries each with `offers.{price, priceCurrency, url}`), `ask` returns a useless answer: "no pricing visible… you'd need to click into individual product pages," with **no** drilldown links and a false `obstacle: empty`. The fetch is fine — the cheapest tier (`raw`) wins in ~1.2s — but the synthetic-markdown adapter that feeds the extractor (`domain.py::json_to_markdown_rows` → `_rows_to_md_table`) **discards every nested field**: it infers columns only from a row's top-level scalars and skips any `dict`/`list` value. For a `Product` row (`@type, name, image, offers`) only `name` and `image` survive — `offers.price`, `offers.priceCurrency`, and `offers.url` are dropped. The extractor therefore sees product names with no prices and no URLs, so it cannot answer price questions, cannot emit `try_url` (the router prompt requires URLs to appear verbatim in content), and mislabels a data-rich page as `obstacle: empty`. The current `extraction` spec already says ItemList rows carry "name and url", so the implementation is non-conformant today.

## What Changes

- The JSON-LD `ItemList` synthesis adapter SHALL lift nested commerce fields into the rendered output: `offers.price` + `offers.priceCurrency` (combined, e.g. `"3690 TRY"`), `offers.url`, and `aggregateRating.ratingValue`.
- Product-shaped listing rows SHALL render as **linked markdown records** (`- [name](url) — 3690 TRY ⭐ 4.7`) rather than a fixed-width table, so the product URL is preserved **verbatim and un-truncated** (the existing table path caps cells at 80 chars, which would mangle long product URLs and re-break `try_url`).
- The synthetic `image` field SHALL be dropped from listing output (image-CDN URLs are pure token noise for the extractor).
- Non-commerce `ItemList` payloads (rows without `price`/`url`) SHALL keep the existing table rendering — no regression for generic lists.
- A deterministic HTML fixture + capability tests SHALL lock the behavior (price, currency, and an un-truncated product URL present in synthesized `content_md`; image URLs absent).

Non-goals (explicitly recorded as scope boundaries; tracked for later changes): extraction of non-JSON-LD embedded state (Trendyol/Yandex custom app-state), browser-tier escalation for bot-walled raw responses (Amazon-class 503), an `obstacle: dynamic`/`needs-js` enum value, and the corpus-wide deterministic replay/refresh eval infrastructure (its own future change).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `extraction`: the **"JSON-LD ItemList synthesis"** requirement changes — synthesized rows carry name, combined price+currency, and an un-truncated product url (and rating when present), rendered as linked markdown records for commerce-shaped lists; image is dropped; non-commerce lists keep table rendering.

## Impact

- Code: `src/a2web/domain.py` (`json_to_markdown_rows` and its helpers — add `_normalize_commerce_row`, add `_rows_to_md_records`, route ItemList/framework-state rows by commerce-shape; `_rows_to_md_table` retained for non-commerce rows).
- Tests: new `tests/fixtures/hepsiburada_listing.html` (trimmed real JSON-LD ItemList, ~5 products); new unit + capability tests under `tests/capabilities/json_extract/` (or `record_extraction/`); regression guard for non-commerce ItemList table rendering.
- Wire/contract: no change to `AskResponse` / `FetchResponse` envelope shape or any tool signature. The improvement surfaces through richer `content_md` the extractor reads, yielding better `answer` + populated `try_url`/`next_links` on listings.
- Performance: linked-record output is comparable in size to the prior table; dropping image-CDN URLs reduces extractor input tokens on listings.
