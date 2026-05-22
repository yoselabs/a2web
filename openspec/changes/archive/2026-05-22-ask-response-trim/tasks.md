## 1. Model layer

- [x] 1.1 In `src/a2web/models.py`, remove `status` from `_ASK_REQUIRED_FIELDS` and add a special case to `AskResponse._omit_empty` that drops the `status` key when its serialized value is `"ok"`.
- [x] 1.2 In `AskResponse._omit_empty`, render a non-empty `next_links` as a TSV string via a helper that uses a2kit's `encode_tsv` over the typed `NextLink` list; columns `anchor`/`url`/`reason`/`kind`, with `kind` dropped when every row's `kind` is `drilldown`.

## 2. Tests (write before implementation wiring)

- [x] 2.1 Test: successful `ask` omits `status`; failed `ask` carries `status == "failed"` (in-process client wire path).
- [x] 2.2 Test: default `ask` has no `extraction` key when the extractor ran without truncation.
- [x] 2.3 Test: a truncated extraction surfaces `operator_hints` entry `code == "answer_truncated"` and still no `extraction` key.
- [x] 2.4 Test: `debug=True` `ask` carries the full `extraction` metadata.
- [x] 2.5 Test: `next_links` is a TSV string — header `anchor`/`url`/`reason` with no `kind` column for an all-drilldown list; `kind` column present for a mixed-kind list.
- [x] 2.6 Update existing `test_ask_response.py` assertions that expect `status` / `extraction: {truncated}` / `next_links` as a JSON array.

## 3. Response builder

- [x] 3.1 In `src/a2web/fetcher_response.py`, change `build_ask_response` so `extraction` is populated only when `debug=True`.
- [x] 3.2 In `build_ask_response`, append an `OperatorHint(code="answer_truncated", ...)` to `operator_hints` when `fr.extraction` reports `truncated`, regardless of `debug`.

## 4. Contract goldens + docs

- [x] 4.1 Re-bless the contract goldens (`make bless-contracts`) and review the diff — `ask_*` scenarios lose `status`/`extraction`, `next_links` becomes TSV, `tool_schemas` reflects any schema shift.
- [x] 4.2 Update `CHANGELOG.md` with the three BREAKING `ask` wire changes; bump the version.
- [x] 4.3 Update `CLAUDE.md` `models.py` note to describe `status` failure-only, `extraction` debug-only, and `next_links` TSV rendering.
- [x] 4.4 Run `make check` (lint + ty + test, coverage ≥85%).
