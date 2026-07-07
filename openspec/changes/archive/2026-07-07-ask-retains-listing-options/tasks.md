## 1. Retain the structured RecordSet

- [x] 1.1 Add `record_set: RecordSet | None` to `FetchContext`; set it in `_escalate_via_records` alongside `record_count`
- [x] 1.2 Thread the retained `RecordSet` through `build_response` onto `FetchResponse` so the ask projection can read it
- [x] 1.3 Test: a parsed listing retains the structured record set on the context/response (not just the count)

## 2. ListingOption model + AskResponse field

- [x] 2.1 Add `ListingOption` pydantic model (`title`, `url`, `detail`) at module scope in `models.py`
- [x] 2.2 Add conditional `options: list[ListingOption]` to `AskResponse`; ensure `_prune_wire` drops it when empty
- [x] 2.3 Test: `options` omitted from the wire when empty (absent, not `null`/`[]`)

## 3. Project records into options (rank-don't-skip)

- [x] 3.1 In `build_ask_response`, project the retained `RecordSet` into `options` — `title` from `heading_text` (text-lead fallback), `url` from `heading_link`, `detail` from the record's own detail text
- [x] 3.2 Gate population on a parsed listing (record set present); page-order preserved, no re-ranking; cap at the ceiling (≈50)
- [x] 3.3 Light `detail` normalization (whitespace collapse + per-detail length cap); no semantic edit
- [x] 3.4 Test: listing ask carries N option entries in page order; non-listing ask omits the field; options are not reordered

## 4. Verification

- [x] 4.1 End-to-end: drive `ask` over a listing fixture through the MCP transport; assert `options` on the wire beside a ranked `answer`, and absent on a non-listing
- [x] 4.2 Re-bless the contract snapshot (`A2WEB_BLESS_CONTRACTS=1`); confirm the diff is purely additive
- [x] 4.3 `make check` green (lint + ty + tests, coverage ≥85%)
- [x] 4.4 Update CHANGELOG.md
- [ ] 4.5 `make bench` after landing (moves listing `ask` payload shape) — deferred, live network
