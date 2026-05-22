## 1. Shared serializer helper

- [x] 1.1 In `src/a2web/models.py`, extract a module-level `_prune_wire(data, *, required, tsv, failure_only)` helper that drops `None`/`[]`/`{}`/`""` values (keeping `required`), special-cases `status` (dropped when `"ok"`), drops `failure_only` fields on success, and substitutes `tsv` entries with their pre-rendered TSV strings.
- [x] 1.2 Rewrite `AskResponse._omit_empty` to delegate to `_prune_wire` — same wire output as today, no duplicated logic (verified: all 28 `test_ask_response.py` assertions + `ask_*` contract goldens pass unchanged).
- [x] 1.3 Generalise the TSV helpers so they serve both `next_links` (`_next_links_tsv` — anchor/url/reason/kind, kind dropped when all-drilldown) and `links` (`_links_tsv` — anchor/href/role).

## 2. FetchResponse serializer

- [x] 2.1 Add a `@model_serializer(mode="wrap")` to `FetchResponse` that delegates to `_prune_wire` with required set `{url, tier, confidence}`, TSV fields `{links, next_links}`, and failure-only `{narrative, diagnostics_summary}`.
- [x] 2.2 Confirm `extraction` / `extracted_answer` drop out naturally on `fetch_raw` (always empty there) — no model field changes.

## 3. Tests (write before wiring)

- [x] 3.1 Test: successful `fetch_raw` omits `status`, `narrative`, `diagnostics_summary`, and all empty optionals (`tests/test_fetch_response.py`, in-process client wire path).
- [x] 3.2 Test: failed `fetch_raw` carries `status == "failed"`, `narrative`, `diagnostics_summary`.
- [x] 3.3 Test: `started_at` / `total_ms` / `cache` / `diagnostics` / `tokens` absent with `debug=False`, present with `debug=True`.
- [x] 3.4 Test: `links` (with `include_links=True`) and `next_links` render as TSV strings; empty arrays stay absent.
- [x] 3.5 Regression guard for `AskResponse` wire output after the `_prune_wire` refactor — covered by the existing `test_ask_response.py` suite (28 assertions) plus the `ask_*` contract goldens, all unchanged.
- [x] 3.6 Updated existing `FetchResponse`-attribute assertions across the suite to the new debug-gated shape (`test_fetcher.py` ×4, `test_archive_escalation.py` ×1 — pass `debug=True` where `cache` / `tokens` are read).

## 4. Response builder

- [x] 4.1 `narrative` / `diagnostics_summary` stay populated on the model (the eval harness reads them); the `FetchResponse` serializer drops them on a successful wire via `_FAILURE_ONLY_FIELDS` — the wire is failure-only as the spec requires, without an internal regression.
- [x] 4.2 In `src/a2web/fetcher_response.py`, `build_response` gates `started_at` / `total_ms` / `cache` / `tokens` population on `fc.debug`; the serializer drops them as empties on the default wire.

## 5. Contract goldens + docs

- [x] 5.1 Re-blessed the contract goldens (`make bless-contracts`); `fetch_raw_basic` drops from 22 keys to 4, `tool_schemas` reflects the nullable timing fields.
- [x] 5.2 Updated `CHANGELOG.md` with the `[0.13.0]` `fetch_raw` BREAKING wire changes; bumped `pyproject.toml` to `0.13.0`.
- [x] 5.3 Updated `CLAUDE.md` `models.py` note to describe the shared `_prune_wire` helper and the `FetchResponse` field tiers.
- [x] 5.4 Ran `make check` — lint, `ty`, and tests all pass (565 passed, coverage 87.62% ≥ 85%).
