## 1. Model layer

- [x] 1.1 Delete `fit_md` from `FetchResponse` and the `fit` field from `TokenCounts` in `src/a2web/models.py`; delete `is_user_authored` from `FetchResponse`.
- [x] 1.2 Add `AskResponse` model to `src/a2web/models.py` at module scope: required `url`, `status`, `tier`, `confidence`, `extracted_answer`; optional `title`, `byline`, `published`, `operator_hints`, `next_links`, `original_url`, `meta`; opt-in `content_md`, `headings`; failure-only `narrative`, `diagnostics_summary`; debug-only `started_at`, `total_ms`, `cache`, `diagnostics`.
- [x] 1.3 Add a slim `AskExtraction` projection (or reuse the serializer) exposing only `truncated` on the default wire path.
- [x] 1.4 Add a `@model_serializer(mode="wrap")` to `AskResponse` that drops keys whose value is `None` / `[]` / `{}` / `""` for the designated optional fields, never dropping required fields.
- [x] 1.5 Add a `@model_serializer` to `Heading` rendering it as a `[level, text]` tuple.

## 2. Tests (write before implementation wiring)

- [x] 2.1 Test: `ask` success returns `AskResponse` with required fields and no `fit_md` / `tokens` / `is_user_authored` (via in-process test client wire path).
- [x] 2.2 Test: default `ask` omits `content_md` and `headings`; `include_content=True` populates both.
- [x] 2.3 Test: empty `byline` / `published` / `operator_hints` / `next_links` / `original_url` / `meta` are absent from the wire; populated ones are present.
- [x] 2.4 Test: `narrative` and `diagnostics_summary` absent on success, present on failure.
- [x] 2.5 Test: `started_at` / `total_ms` / `cache` / `diagnostics` absent with `debug=False`, present with `debug=True`.
- [x] 2.6 Test: `extraction` carries only `truncated` with `debug=False`, full metadata with `debug=True`.
- [x] 2.7 Test: `Heading` serializes as `[level, text]` on `fetch_raw`.
- [x] 2.8 Test: HN front-page fixture — external-link story line carries both article and discussion URLs; text-only story carries the discussion URL; `next_links` stays one entry per story.
- [x] 2.9 Update existing `fit_md` / `is_user_authored` assertions across the test suite to the new shape.

## 3. Response builder

- [x] 3.1 Add `build_ask_response(fc)` to `src/a2web/fetcher_response.py` producing `AskResponse`; apply failure-only logic for `narrative` / `diagnostics_summary`.
- [x] 3.2 Remove `fit_md` population and `TokenCounts.fit` references from `build_response`.
- [x] 3.3 Gate `content_md` / `headings` population on the `include_content` flag threaded through `FetchContext`.

## 4. Tool surface

- [x] 4.1 Add `include_content: bool = False` param to `WebRouter.ask` in `src/a2web/routers.py`; thread it through `orchestrate`.
- [x] 4.2 Change `ask`'s return annotation to `AskResponse`; route it through `build_ask_response`.
- [x] 4.3 Thread `include_content` into `FetchContext` and the orchestrator in `src/a2web/fetcher.py`.

## 5. HN handler

- [x] 5.1 Update `_render_front_page` in `src/a2web/handlers/hn.py` to emit both article and discussion URLs per story line.
- [x] 5.2 Confirm `_front_page_candidates` keeps one `NextLink` per story (no discussion-URL duplicate).

## 6. Golden contract tests

- [x] 6.1 Add a `tests/contracts/` golden harness: a helper that invokes a tool via the in-process test client, normalizes non-deterministic fields, and compares to (or blesses) a golden JSON. `A2WEB_BLESS_CONTRACTS=1` rewrites goldens; mismatch failure message explains the bless path.
- [x] 6.2 Add the deterministic HN front-page fixture (`tests/fixtures/hn_front_page.json`), shared by task 2.8 and the contract scenarios.
- [x] 6.3 Capture golden files for `ask_success_minimal`, `ask_success_rich`, `ask_failure`, `ask_include_content`, `ask_debug`, `fetch_raw_basic`.
- [x] 6.4 Add a `bless-contracts` target to the Makefile.
- [x] 6.5 (Optional) Snapshot the generated MCP tool output schema for `ask` and `fetch_raw` as a one-file contract.

## 7. Docs and release

- [x] 7.1 Add an entry to `docs/history/A2KIT_FEEDBACK_v0.*.md` requesting formatter-level `exclude_none` / `exclude_defaults` support so the custom serializer can be retired.
- [x] 7.2 Update `CHANGELOG.md` with the BREAKING `ask` envelope change and the `include_content` escape hatch; bump the version.
- [x] 7.3 Update `CLAUDE.md` `models.py` / `routers.py` notes to describe `AskResponse` vs `FetchResponse` and the `include_content` param.
- [x] 7.4 Run `make check` (lint + ty + test, coverage ≥85%).
