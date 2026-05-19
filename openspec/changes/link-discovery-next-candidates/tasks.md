## 1. Model + response envelope

- [x] 1.1 Add `NextLink` pydantic model at module scope in `src/a2web/models.py` (fields: `anchor`, `url`, `reason`, `kind`; `max_length` validators with truncation)
- [x] 1.2 Add `next_links: list[NextLink] = Field(default_factory=list)` to `FetchResponse` (additive, ordered before `diagnostics` for readability)
- [x] 1.3 Add unit test `tests/test_models.py::test_next_link_caps_anchor_and_reason` covering truncation and invalid `kind`

## 2. Tier 1 — TierResult plumbing

- [x] 2.1 Add `next_links: list[NextLink] = field(default_factory=list)` to the `TierResult` dataclass in `src/a2web/tiers/__init__.py`
- [x] 2.2 Update `_install_won_tier` / `_install_archive_payload` in `src/a2web/fetcher.py` to thread `tier_result.next_links` into `FetchContext.next_links_handler`
- [x] 2.3 Add a `next_links_handler: list[NextLink] = field(default_factory=list)` slot on `FetchContext`

## 3. Tier 1 — handler population

- [x] 3.1 Reddit: extend `RedditHandler.matches()` to also match `/r/<sub>/` and `/r/<sub>/{hot,new,top,rising}/`; branch in `fetch()` between listing and permalink paths; populate top-10 permalinks with NSFW filter
- [x] 3.2 Reddit: add fixture `tests/fixtures/reddit/listing-locallama-25-with-3-nsfw.json` and tests covering listing match, top-10 selection, NSFW filter, permalink-empty
- [x] 3.3 HN: extend `HNHandler.matches()` for `https://news.ycombinator.com/` + `/news`; add `_render_front_page()` calling the Algolia `tags=front_page` search; populate up-to-10 candidates with external-url / item-url branch
- [x] 3.4 HN: add fixture + tests for front-page match, external-link branch, text-only branch, item-URL-empty
- [x] 3.5 arXiv: extend `ArxivHandler.matches()` for `/list/<cat>/<yymm>` and `/list/<cat>/recent`; parse listing HTML; populate up-to-10 abs candidates with authors as `reason`
- [x] 3.6 arXiv: add fixture + tests for category-listing match, candidate shape, abs-URL-empty
- [x] 3.7 GitHub: extend repo path in `GitHubHandler` to call `/issues?state=open` (top 5) + `/pulls?state=open` (top 5) and emit `kind="related"` candidates; issue/PR URLs return empty
- [x] 3.8 GitHub: add fixture + tests for repo-URL candidates, issue-URL-empty, PR-URL-empty
- [x] 3.9 Wikipedia: parse top-10 outbound wikilinks from Parsoid HTML; emit `kind="related"`; assert host equals source language wiki
- [x] 3.10 Wikipedia: add fixture + tests for wikilink population and same-language-host invariant

## 4. Tier 2 — LLM curation in the ask= call

- [x] 4.1 Extend the `ask=` extraction prompt in `src/a2web/packages/llm_extract/prompts.py` with the `next_links` instructions block (kinds, cap, URL-must-be-in-markdown rule, ≤80-char reason)
- [x] 4.2 Extend the provider response schema in `src/a2web/packages/llm_extract/extractor.py` to accept optional `next_links: list[NextLink]`; absent field → empty list
- [x] 4.3 Add `_validate_candidates_url_in_markdown(candidates, markdown) -> tuple[kept, dropped]` helper; emit `Diagnostic(verdict=extraction_drift, ...)` for each dropped URL
- [x] 4.4 Wire the validated list back into `FetchContext.next_links_llm` from the extract phase
- [x] 4.5 Add unit test covering single-call shape: one provider invocation returns both `answer` and `next_links`
- [x] 4.6 Add unit test for URL-not-in-markdown drift: provider returns a hallucinated URL → drift diagnostic, candidate dropped

## 5. Composition rule + final assembly

- [x] 5.1 Add `_phase_compose_candidates(fc: FetchContext) -> list[NextLink]` to `src/a2web/fetcher.py`: when handler list non-empty AND `ask=` set, pass handler list into the extract prompt as additional context and use the LLM-returned list (Tier 2 replaces Tier 1)
- [x] 5.2 When handler list non-empty AND `ask=` absent, return the handler list unchanged
- [x] 5.3 When handler list empty AND `ask=` set, return the LLM list (already validated in step 4)
- [x] 5.4 When both empty, return `[]`
- [x] 5.5 Enforce the cap=10 trim as the last step before writing to the response
- [x] 5.6 Add integration test in `tests/test_link_discovery_composition.py` for all four matrix cells

## 6. Tool parameter

- [x] 6.1 Add `next_links: Annotated[bool, pydantic.Field(default=True, description="...")]` to the `fetch` tool signature in `src/a2web/routers.py`
- [x] 6.2 When `False`, force `FetchResponse.next_links = []` regardless of computed value
- [x] 6.3 Add unit test covering the suppression flag

## 7. Provider re-rank prompt for Tier 1+2 composition

- [x] 7.1 In `prompts.py`, add the "re-rank these handler-supplied candidates against the question" system message used when handler candidates are passed in
- [x] 7.2 Add unit test feeding handler candidates + a question; assert the LLM-returned list's `reason` strings reference the question

## 8. Independence + lint

- [x] 8.1 Verify `pytest tests/test_packages_independence.py` stays green
- [x] 8.2 Run `make lint` and `make ty`; resolve any new diagnostics

## 9. Docs + changelog + backlog cleanup

- [x] 9.1 Add "Link discovery — `next_links`" subsection to README under the fetch-tool reference; one Reddit-listing drilldown example
- [x] 9.2 Add CHANGELOG entry under v0.7 "Added"
- [x] 9.3 Remove the v0.4+ "discovery / next-link curation" entry from `BACKLOG.md` (now shipped here)
- [x] 9.4 Update the v0.4+ "alias-addressed links" entry in `BACKLOG.md` with a forward reference to this change as the prerequisite

## 10. Benchmark re-run

- [ ] 10.1 Re-run `benchmarks/vs-webfetch/2026-05-11/` against PyPI / gh-trending / Reddit listing URLs
- [ ] 10.2 Add a `next_links_picked_correctly` judge axis to the benchmark prompts
- [ ] 10.3 Capture results in `benchmarks/vs-webfetch/<new-date>/findings.md`

## 11. Verify the gate

- [x] 11.1 `make check` passes (lint + ty + test, coverage ≥85%)
- [ ] 11.2 In-process MCP smoke: `make dev` then `fetch` a Reddit listing + assert `next_links` present in tool result
