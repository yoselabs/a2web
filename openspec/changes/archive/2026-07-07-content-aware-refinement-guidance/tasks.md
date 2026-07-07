## 1. Context bundle (deterministic, no interpretation)

- [x] 1.1 Add a pure helper that parses a URL's query string into opaque `key=value` pairs (parsed, uninterpreted; non-raising on malformed/empty)
- [x] 1.2 Assemble the context bundle (URL + parsed params + computed kind + `items_loaded`/`items_total`) on `FetchContext` / the response builder in `fetcher_response.py`
- [x] 1.3 Surface the parsed query params as reasoning fuel: on `fetch_raw` in the envelope for the caller's model; on `ask` into the extraction input
- [x] 1.4 Test: params surfaced verbatim, no param labeled as sort/filter; malformed query degrades gracefully

## 2. Content-type guidance (per-kind, never per-site)

- [x] 2.1 Add a guidance fragment table keyed on the closed content-kind enums (`listing` / `discussion` / `article` / `product`), containing no host/domain/site strings
- [x] 2.2 Compose the selected fragment into the server-side extraction system prompt in `packages/llm_extract/prompts.py` on the `ask` path
- [x] 2.3 Architecture test: assert the guidance table contains no site/host string (per-kind only)
- [x] 2.4 Test: `listing` kind selects completeness+bias+axes guidance; static MCP `list_tools` description is unchanged per-fetch

## 3. LLM-side partialness detection (close the language gap)

- [x] 3.1 Extend the `ask`-path extractor to judge partialness from content-in-hand (repeated item structure + a readable total the regex noun list may miss)
- [x] 3.2 Wire the detection as a superset: listing is partial when regex oracle OR LLM-side judgment trips; LLM-side never suppresses an existing signal
- [x] 3.3 Test: non-covered-language total (`товаров` / `件`) where regex yields `None` is caught LLM-side; regex fast-path still fires alone; LLM-side never removes a completeness verdict

## 4. Dimensional refinement axes (ask path)

- [x] 4.1 Add the refinement-axes reasoning to the extraction prompt: propose dimensions to re-query on, forbidden from emitting values drawn from the retrieved sample
- [x] 4.2 Parse the axes through the existing `wobble` funnel (`parse_list_with_policy`); no new `json.loads` site
- [x] 4.3 Add the conditional `refinement_axes` field to `AskResponse` in `models.py`; wire omit-empty via `_prune_wire`
- [x] 4.4 Gate emission on `partial AND kind==listing`; omit on complete/non-listing
- [x] 4.5 Test: sorted/truncated sample yields axes not values; complete listing and non-listing omit the field (absent, not `null`/`[]`)

## 5. Verification

- [x] 5.1 `make check` green (lint + ty + tests, coverage ≥85%)
- [x] 5.2 Add/extend capability tests under `tests/capabilities/` for `refinement-guidance` scenarios
- [ ] 5.3 `make bench` after landing (moves output shape/quality on listing URLs); write findings to `eval/findings_<date>.md`
- [x] 5.4 Update CHANGELOG.md with the version bump entry
