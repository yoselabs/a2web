## 1. Model fields

- [x] 1.1 The six debug fields (`started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, `extraction`) stay declared flat on `AskResponse` / `FetchResponse` — no `DebugInfo` model, no `debug` field. The `debug` nesting is wire-only (the serializer regroups; see task 2).
- [x] 1.2 Remove `original_url` from `AskResponse` and `FetchResponse`.

## 2. _prune_wire deviation + debug regrouping

- [x] 2.1 Generalize `_prune_wire` with a `deviation: dict[str, str]` parameter — a field is dropped when its value equals the mapped default. Fold the existing hardcoded `status == "ok"` rule into this map.
- [x] 2.2 Add a `debug_fields: frozenset[str]` parameter to `_prune_wire` — matching keys are pruned of empties and collected under `out["debug"]` instead of staying top-level; no `debug` key is emitted when all debug fields are empty.
- [x] 2.3 Update both serializers: pass `deviation=_WIRE_DEVIATION` (`{status: ok, tier: raw}`) and the debug-field set. Remove `url` and `tier` from the required-field sets (`_ASK_REQUIRED_FIELDS` → `{confidence, extracted_answer}`, `_FETCH_REQUIRED_FIELDS` → `{confidence}`).

## 3. Response builders

- [x] 3.1 `build_response` keeps gating timing / cache / tokens population on `fc.debug` (unchanged from fetch-response-diet); the serializer now regroups them.
- [x] 3.2 `build_response` sets the `url` field to `fc.final_url` only when it differs from the requested URL, else to `""`. Added `FetchContext.requested_url` (captured once at `fetch()` entry, never mutated by captcha or after-tier rewrites) as the stable comparison input.
- [x] 3.3 `build_response` no longer populates `original_url`; the field is deleted from `FetchResponse` and the now-dead `FetchContext.original_url` field is removed too.
- [x] 3.4 `build_ask_response` drops the `original_url` projection; the truncation → `answer_truncated` operator hint still fires regardless of `debug`.
- [x] 3.5 Verified no internal caller reads `FetchResponse.url` — the eval harness reads `.extraction` / `.tier` / `.status` / `.diagnostics_summary` (all still flat) but never `.url`. No fix needed; builder-gating `url` is safe.

## 4. Tests (write before wiring)

- [x] 4.1 Test: default `ask` / `fetch_raw` carry no `debug` key and no top-level `started_at` / `total_ms` / `cache` / `diagnostics` / `tokens` / `extraction`.
- [x] 4.2 Test: `debug=True` `ask` / `fetch_raw` carry a `debug` object with the full trace nested inside; `ask` debug carries `debug.extraction`.
- [x] 4.3 Test: `tier` absent on the `raw` tier; present when a site handler won.
- [x] 4.4 Test: `url` absent when the fetched URL equals the requested URL; present (final URL) after a captcha-host rewrite.
- [x] 4.5 Test: neither envelope ever emits `original_url`.
- [x] 4.6 Updated existing assertions: `ask` / `fetch_raw` wire tests for the nested `debug` object and deviation-gated `tier` / `url`; the captcha tests in `test_fetcher.py` (`original_url` removed → assert on `result.url` deviation).

## 5. Contract goldens + docs

- [x] 5.1 Re-blessed the contract goldens (`make bless-contracts`); `fetch_raw_basic` is 2 keys, `ask_debug` nests the trace under `debug`.
- [x] 5.2 Updated `CHANGELOG.md` with the `[0.14.0]` BREAKING wire changes; bumped `pyproject.toml` to `0.14.0`.
- [x] 5.3 Updated `CLAUDE.md` `models.py` note — `_prune_wire` deviation + debug-regroup params, wire-only `debug` object, deviation-only `tier` / `url`, `original_url` removed.
- [x] 5.4 Ran `make check` — lint, `ty`, and tests all pass (572 passed, coverage 87.64% ≥ 85%).
