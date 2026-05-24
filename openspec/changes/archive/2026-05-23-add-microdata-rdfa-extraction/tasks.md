## 1. Dependency

- [ ] 1.1 Add `extruct>=0.18,<1` to `pyproject.toml` `[project] dependencies`. Run `uv lock`. Confirm transitive deps land: `rdflib`, `mf2py`, `jstyleson`, `w3lib`.
- [ ] 1.2 Confirm the lockfile resolution does not conflict with existing `cryptography` / `lxml` pins (extruct uses lxml ≥ 4 — should align with trafilatura's pin).

## 2. Widen JsonSource literal + boundary documentation

- [ ] 2.1 In `src/a2web/packages/json_in_script.py`, widen `JsonSource = Literal[...]` to add `"microdata" | "rdfa" | "opengraph"`. Confirm `"window_var"` is already in the Literal (close the existing code-vs-spec drift in this change).
- [ ] 2.2 Update the module docstring's Gherkin block to mention the three new sources.
- [ ] 2.3 Update the `JsonPayload` docstring: clarify that `script_id` is `None` for extruct-sourced payloads.

## 3. Extraction

- [ ] 3.1 In `extract_json_payloads`, after the existing script-tag scans, call `extruct.extract(html, syntaxes=["microdata", "rdfa", "opengraph"], uniform=True)` exactly once and wrap each non-empty syntax bucket into `JsonPayload` records.
- [ ] 3.2 Each extruct-sourced payload SHALL set `byte_size = len(json.dumps(data))` and `script_id = None`.
- [ ] 3.3 Wrap the extruct call in try/except — extruct's RDFa path can raise on malformed attribute sets; those SHALL be silently skipped (consistent with the existing JSON-parse-failure scenario).
- [ ] 3.4 Confirm the call lives inside `extract_json_payloads` so the `asyncio.to_thread` wrap at `_phase_extract` in `fetcher.py` covers it. Do NOT add a nested to_thread.

## 4. Ranking

- [ ] 4.1 In `rank_payloads`, extend the `bucket(p)` function to return:
  - 0 for `ld_json` strong (existing)
  - 1 for `microdata` strong (new — reuses the `_ld_json_strong` predicate over the flattened microdata dict)
  - 2 for `next_data` / `nuxt_data` (existing, renumbered)
  - 3 for `opengraph` (new)
  - 4 for `ld_json` weak, `microdata` weak (existing + new)
  - 5 for `window_var` (existing, renumbered)
  - 6 for `generic` (existing, renumbered)
  - 7 for `rdfa` (new — last)
- [ ] 4.2 Add a `_microdata_strong(data: dict | list) -> bool` helper mirroring `_ld_json_strong` semantics: at least one `@type` in `{Product, Article, ItemList, BreadcrumbList, NewsArticle}` with ≥3 populated non-`@`-prefixed fields.

## 5. Domain adapters

- [ ] 5.1 In `src/a2web/domain.py::json_to_markdown_rows`, add dispatch for `source="microdata"`. Implement `_microdata_to_ld_shape(data)` flattener so the existing `_ld_json_to_markdown` walker can consume it. Extruct's microdata output already nests `properties` under `type`; the flattener maps `type` → `@type`, `properties` → direct keys.
- [ ] 5.2 Add `_opengraph_to_markdown(data)` — render as a two-column markdown table over the OG namespaces (`og`, `article`, `product`, `book`, `profile`). Skip blank values. Cap at ~50 rows.
- [ ] 5.3 Add `_rdfa_to_markdown(data)` — render as a three-column markdown table (`subject | predicate | object`). Truncate at 30 rows.
- [ ] 5.4 Confirm `domain.py` continues to live at module scope (no nested classes) and continues to import only from `packages/` boundary types.

## 6. Tests

- [ ] 6.1 Add fixture `tests/fixtures/structured/microdata_product.html` (real Shopify-class product page snapshot). Scenario test: extractor returns one `JsonPayload(source="microdata")`; `_microdata_strong` returns True; `rank_payloads` puts it ahead of an injected `next_data` payload.
- [ ] 6.2 Add fixture `tests/fixtures/structured/rdfa_scholarly.html` (academic page with RDFa). Scenario test: extractor returns one `JsonPayload(source="rdfa")`; bucket lands at the bottom.
- [ ] 6.3 Add fixture `tests/fixtures/structured/opengraph_product.html` (page with rich OG attributes). Scenario test: extractor returns one `JsonPayload(source="opengraph")`; bucket lands at 3.
- [ ] 6.4 Add a malformed-RDFa fixture. Scenario test: extruct exception is swallowed; other syntaxes still emit.
- [ ] 6.5 Add a microdata→markdown snapshot test confirming the flattener produces a markdown surface comparable to the LD-JSON equivalent.
- [ ] 6.6 Confirm `tests/test_packages_independence.py` continues to pass.

## 7. Eval corpus

- [ ] 7.1 Add at least one microdata-only entry to `eval/corpus.yaml` (e.g., a Shopify product page). Add at least one OG-only entry (e.g., a long-tail news article).
- [ ] 7.2 Document the entries in `eval/corpus.yaml`'s commentary so future maintainers know they are the structured-data-coverage canaries.

## 8. Verification

- [ ] 8.1 Run `make check` (lint + ty + test-cov ≥85%). All green.
- [ ] 8.2 Run `make bench` against the expanded corpus. Compare four-axis scores against the previous run. Confirm answer quality lifts on the microdata + OG entries.
- [ ] 8.3 If `make bench` shows p50 fetch-time regression > 5%, file a follow-up task: ship `AppSettings.disable_rdfa` (default `False`) as a kill switch; do NOT block this change on it.
- [ ] 8.4 Manually trigger a fetch against a Shopify-class product URL through Claude Code MCP. Confirm `pre_rendered.content_md` carries the microdata-derived product surface.

## 9. Ship

- [ ] 9.1 Bump version in `pyproject.toml`.
- [ ] 9.2 Update `CHANGELOG.md` — note the new capability (microdata + RDFa + OG support), the new dependency (extruct), the four-axis bench delta.
- [ ] 9.3 Run `make install-global`.
- [ ] 9.4 Archive this change via the openspec workflow.
