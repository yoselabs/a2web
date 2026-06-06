## 1. Fixture

- [x] 1.1 Create `tests/fixtures/hepsiburada_listing.html`: a minimal HTML shell containing the real `<script type="application/ld+json">` `ItemList` block trimmed to ~5 real `Product` items, each with `name`, `image`, `offers.{price, priceCurrency, url}`, and `aggregateRating.ratingValue`. Keep it ~1–2 KB, consistent with existing fixtures. Include at least one product whose `offers.url` exceeds 80 characters.
- [x] 1.2 Export the fixture path via `tests/fixtures/__init__.py` (`FIXTURES_DIR`) if not already discoverable.

## 2. Tests first (red)

- [x] 2.1 Unit test on `domain.json_to_markdown_rows` / `_ld_json_to_markdown`: given the fixture's JSON-LD `ItemList`, assert the output is linked-record form containing a full `[<name>](<https://…-pm-HBC…>)` link, a `3690 TRY`-style combined price token, and a lifted rating; assert no `productimages.hepsiburada.net` image URL appears.
- [x] 2.2 Unit test for the long-URL case: assert the >80-char product url appears verbatim and un-truncated in the rendered record.
- [x] 2.3 Capability test (trendyol-style) under `tests/capabilities/json_extract/`: drive `_run_extraction_escalation(fc, raw_html=<fixture html>)` and assert `3690`, `TRY`, and a `-pm-HBC` product URL are present in `fc.content_md`.
- [x] 2.4 Regression guard: a non-commerce `ItemList` (rows without `price`/`url`) still renders as a fixed-width markdown table, not linked records.
- [x] 2.5 Sanitization test: a product `name` containing `]`/`)`/newline does not break the markdown link.
- [x] 2.6 Confirm 2.1–2.5 fail against current `domain.py` (red), proving they exercise the gap.

## 3. Implementation (green)

- [x] 3.1 Add `_normalize_commerce_row(row: dict) -> dict` in `src/a2web/domain.py`: promote `offers.price`+`offers.priceCurrency` → combined `price` string, `offers.url` → `url`, `aggregateRating.ratingValue` → `rating`; leave flat-shaped and non-commerce rows untouched.
- [x] 3.2 Add `_rows_to_md_records(rows: list[dict], *, title: str) -> str`: render `- [<name>](<url>) — <price> ⭐ <rating>` per row, omitting absent fields, sanitizing link text, no URL length cap, capped at 50 rows.
- [x] 3.3 Add a commerce-shape predicate (≥ half of rows carry a lifted `price` or `url`).
- [x] 3.4 Route in `_ld_json_to_markdown` (ItemList branch) and `_framework_state_to_markdown`: normalize rows, then render via `_rows_to_md_records` when commerce-shaped, else fall back to existing `_rows_to_md_table`.
- [x] 3.5 Stop emitting the `image` field for listing rows.
- [x] 3.6 Update `__all__` / any export if helper visibility changes; keep `_rows_to_md_table` intact for non-commerce rows.

## 4. Verify

- [x] 4.1 Run the new tests — all green.
- [x] 4.2 `make check` passes (lint + ty + test, coverage ≥85%).
- [x] 4.3 Live sanity: `a2web web ask --url=https://www.hepsiburada.com/mikrofon-aksesuarlari-c-411155 --question="what is the cheapest microphone and its price?"` returns a real cheapest-item answer with a populated `try_url`/`next_links` and no `obstacle: empty`. (Manual, live-network — not part of `make check`.)

## 5. Archive

- [x] 5.1 Update `CHANGELOG.md` with the listing offer-lift entry.
- [ ] 5.2 Run `openspec archive listing-offer-lift` after merge (folds the `extraction` spec delta into `openspec/specs/extraction/spec.md`).
