## Why

`ask-response-diet` + `ask-response-trim` made the `ask` envelope lean, but `fetch_raw` still returns the raw `FetchResponse` with every field — see a real `fetch_raw` payload: 22 keys, most of them `null` / `[]` / `{}` (`byline: null`, `links: []`, `meta: {}`, `extraction: null`, `extracted_answer: null`, `next_links: []`, `original_url: null`, …). `fetch_raw` is the fallback tool (~5% of reads) but still pays the full clutter tax on every call. The same diet that worked for `ask` applies here.

## What Changes

- **BREAKING** — `FetchResponse` omits empty/null optional fields from the wire (`title`, `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `diagnostics`, `extraction`, `extracted_answer`) via a `@model_serializer`, instead of serializing them as `null` / `[]` / `{}`. On `fetch_raw` the LLM fields (`extraction`, `extracted_answer`) are always empty, so they simply disappear.
- **BREAKING** — `status` is failure-only on `FetchResponse` (omitted when `ok`, present on `failed` / `partial`) — same rule `ask` already uses.
- **BREAKING** — `narrative` and `diagnostics_summary` are failure-only; `started_at`, `total_ms`, `cache`, `diagnostics`, and `tokens` move to `debug`-only.
- **BREAKING** — `next_links` and `links` render as TSV blocks (header + rows) instead of JSON arrays of objects, mirroring `ask`. `next_links` drops its `kind` column when every row is `drilldown`.
- The omit-empty + TSV serialization logic is shared between `AskResponse` and `FetchResponse` via a common helper rather than duplicated.

## Capabilities

### New Capabilities
- `fetch-response`: the `fetch_raw` / `FetchResponse` wire envelope — empty-field omission, failure-only `status` / `narrative`, debug-only timing & `tokens`, TSV rendering for `links` and `next_links`.

## Impact

- `src/a2web/models.py` — `FetchResponse` gains a `@model_serializer`; the empty-omission + TSV helpers are extracted for reuse by `AskResponse` and `FetchResponse`.
- `src/a2web/fetcher_response.py` — `build_response` populates `narrative` / `diagnostics_summary` only on non-ok status; timing/`tokens` gating moves to the serializer tier.
- `tests/` — contract golden `fetch_raw_basic` re-blessed; `FetchResponse`-wire assertions updated. `fetch()` callers reading attributes (eval harness, unit tests) are unaffected — the serializer is wire-only.
- BREAKING for `fetch_raw` MCP consumers parsing the old always-present field set. `ask` / `AskResponse` are unaffected (already lean).
