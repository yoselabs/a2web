## 1. Ask-First sign-off

- [x] 1.1 Confirm the envelope shape change (`ListingOption` new fields) with the user before writing any implementation code, per `AGENTS.md` Ask First — this is a required gate, not optional process.

## 2. Normalization — lift the fields already in hand

- [x] 2.1 Extend `_normalize_commerce_row` (`src/a2web/packages/structured_render.py:483`) to read `offers.availability` → `stock` and `offers.seller.name` → `seller`, alongside the existing price/currency/rating lift.
- [x] 2.2 Stop pre-joining `price` + `priceCurrency` into one string in `_normalize_commerce_row`; keep them as separate output keys.
- [x] 2.3 Update the markdown renderer (`_render_rows` / `_rows_to_md_records`) to join `price` + `currency` back into one display string at render time, so `content_md` output is unchanged (per design D3).
- [x] 2.4 Add/extend a unit test on `_normalize_commerce_row` covering: price+currency split into separate keys, availability lifted to `stock`, seller lifted to `seller`, and each individually absent when the source `offers` dict doesn't carry it.

## 3. Carry typed fields through to `ListingOption`

- [x] 3.1 In `_rows_to_record_set` (`ladder.py:198`, JSON-LD/framework-state path only), retain the normalized row dict alongside each `Record` it builds — position-keyed within the same loop, per design D2. Do not modify `record_mine.Record` (shelf-owned).
- [x] 3.2 Add `price: str | None`, `currency: str | None`, `rating: str | None`, `stock: str | None`, `seller: str | None` fields to `ListingOption` in `src/a2web/models.py`, all optional/omit-empty, matching the existing wire discipline.
- [x] 3.3 Update `_records_to_options` (`fetcher_response.py:435`) to populate the new typed fields from the carried normalized-row data when present (JSON-LD path), and leave them unset when absent (DOM-mined path) — no re-parsing of `detail`/`Record.text`.
- [x] 3.4 Add a row-identity test (per design Risks) asserting a `ListingOption`'s typed fields pair with the correct row — not just field presence — to guard the position-keyed carry against future row-filtering drift between the two lists.

## 4. Tests and contracts

- [x] 4.1 Extend `tests/capabilities/link_affordances/test_json_ld_listing_index.py` — JSON-LD-sourced options carry typed fields; DOM-mined options (including the both-present precedence case) carry none.
- [x] 4.2 Extend `tests/capabilities/ask_response/test_listing_options.py` — typed fields present/absent per source, `stock`/`seller` individually omitted when not in the source declaration.
- [x] 4.3 Extend `tests/capabilities/link_affordances/test_option_shelf_byte_budget.py` (or add alongside it) confirming the new scalar fields don't meaningfully change the existing per-option byte budget.
- [x] 4.4 Run `make check` (lint + ty + test, coverage ≥85%).
- [x] 4.5 Mutation-verify: mutate the new field-population logic, confirm the relevant test(s) go red for the right reason, restore, re-verify green (session convention — never `git checkout --` on an uncommitted file; precise `Edit` restore only).
- [x] 4.6 Re-bless wire contract goldens: `make bless-wire SLUG=<reason>`; confirm the diff is exactly the new additive fields. — N/A: `uv run pytest tests/contracts/ -q` (36/36) passed unchanged; no golden fixture exercises a JSON-LD listing, so there is no delta to bless.
- [x] 4.7 Run `make recon-check`.

## 5. Docs and close-out

- [x] 5.1 Sync `openspec/specs/ask-response/spec.md` with the delta in this change (via `openspec-sync-specs` / `opsx:sync`, or at archive time).
- [x] 5.2 Update `ListingOption`'s docstring in `models.py` to state typed fields are JSON-LD-sourced only, per the Risks note in design.md (absence doesn't mean the page lacks the data).
- [x] 5.3 Close `a2web-gvy` with a reason summarizing what shipped vs. the audit's full ask (typed fields shipped; DOM-text mining and product-page backfill explicitly out of scope, per design Non-Goals).
- [ ] 5.4 Archive this change (`openspec-archive-change` / `opsx:archive`) once merged.
