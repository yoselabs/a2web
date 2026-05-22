## Why

`ask-response-diet` cut the bulk, but three small things in the `ask` envelope still cost tokens without carrying signal: `extraction: {truncated: false}` is a zero-information object on nearly every response; `status: "ok"` restates what the presence of `extracted_answer` already implies; and `next_links` repeats its four JSON keys (`anchor`/`url`/`reason`/`kind`) on every row.

## What Changes

- **BREAKING** — `extraction` leaves the default `ask` wire entirely; it is `debug`-only. When the extractor truncated its input (the page exceeded `max_content_chars`, so the answer was built from a partial read), that surfaces as an `operator_hint` with `code: "answer_truncated"` instead of a one-field object. `extraction: {truncated: false}` no longer appears anywhere.
- **BREAKING** — `status` becomes failure-only on `ask`: omitted when `ok`, present on `failed` / `partial`. Joins `narrative` and `diagnostics_summary` in the failure-only tier — absence of `status` means success.
- **BREAKING** — `next_links` on `ask` renders as a TSV block (a header row plus one tab-separated row per link) instead of a JSON array of objects. The `kind` column is dropped when every row is `drilldown` (the common case), and re-added when the list is mixed.

## Capabilities

### Modified Capabilities
- `ask-response`: `extraction` is `debug`-only with truncation surfaced as an operator hint; `status` is failure-only; `next_links` renders as a TSV block.

## Impact

- `src/a2web/models.py` — `AskResponse` `@model_serializer`: drop `status` when `ok`, render `next_links` as TSV; `status` leaves the never-omit required set.
- `src/a2web/fetcher_response.py` — `build_ask_response`: truncation → `answer_truncated` operator hint; `extraction` populated only under `debug`.
- `tests/test_ask_response.py`, `tests/test_contracts.py` — updated assertions; contract goldens re-blessed.
- BREAKING for `ask` consumers reading `extraction` on the default path, branching on `status == "ok"`, or parsing `next_links` as a JSON array. `fetch_raw` / `FetchResponse` are unaffected.
