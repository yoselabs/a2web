## 1. HN Algolia search handler (P3)

- [x] 1.1 Write failing tests for `HNHandler.matches()`: claims `hn.algolia.com/?q=<query>`, rejects `hn.algolia.com/` with no `q`, still claims `news.ycombinator.com` front-page + item URLs
- [x] 1.2 Write failing test for `HNHandler.fetch()` on an Algolia search URL: issues GET to `/api/v1/search?query=<q>&tags=story&hitsPerPage=30`, returns `verdict==ok` with `pre_rendered` story list + populated `next_links` (stub transport with a captured Algolia search payload)
- [x] 1.3 Write failing test that an upstream non-2xx from the Algolia API returns the centralized non-OK mapping (surfaces status), not a silent empty success
- [x] 1.4 Extend `HNHandler.matches()` to accept `host == "hn.algolia.com"` with a non-empty `q` param
- [x] 1.5 Extend `HNHandler.fetch()` to build the Algolia search `api_url` for the search shape and flow through the existing JSON-parse → `_render_front_page` → `TierResult(pre_rendered, next_links=_front_page_candidates(...))` path
- [x] 1.6 Confirm the handler is discovered by `match_handler` / the handler manifest with no manifest change needed (same `HNHandler` class)
- [x] 1.7 Run the P3 tests green; add a `handler-live-probe`-style probe entry for the Algolia search URL if that harness expects one

## 2. Confabulation guard — obstacle → confidence / status (P2)

- [x] 2.1 Write failing tests (ask path) for confidence reconciliation: `obstacle: empty` over >2000 chars yields `confidence: low`; `obstacle: blocked` yields `low`; healthy page (no obstacle) keeps its `(verdict, length)` confidence; `fetch_raw` is unaffected
- [x] 2.2 Write failing tests for retrieval-incompleteness: `obstacle ∈ {empty, blocked}` sets `retrieval_incomplete=true` + a `retrieval_incomplete` operator hint; `obstacle ∈ {paywalled, error}` caps confidence but does not force `retrieval_incomplete` here; no obstacle → nothing added
- [x] 2.3 Implement the reconciliation in the ask-path projection (`build_ask_response` / `_project_routing`) — where `obstacle` reaches the wire — NOT in `build_response` (obstacle is `None` there; see design D2). Downgrade-only: never raise confidence
- [x] 2.4 Add the `retrieval_incomplete` `OperatorHint` (code + message naming the likely cause) for the empty/blocked case
- [x] 2.5 Verify the guard composes correctly with the existing `extraction_empty` / `llm_unavailable` guards (no double-flagging, consistent `status`/`retrieval_incomplete`)
- [x] 2.6 Run the P2 tests green

## 3. Paid-render escalation for js_required SPA shells (P1)

- [x] 3.1 Write failing planner tests for `_decide_paid_last_resort`: fires `EscalatePaid` on `length_floor` + subsystem `js_required` when browser rung spent and `paid_dispatches < 1`; does NOT fire on bare `length_floor` (no subsystem); does not re-fire when `paid_dispatches == 1`
- [x] 3.2 Extend the paid last-resort rule to recognize the `length_floor` + `js_required` wall (companion condition alongside `_PAID_WALL_VERDICTS` — keep the subsystem gate; do not add bare `length_floor` to `_PAID_WALL_VERDICTS`)
- [x] 3.3 Confirm the dispatched paid tier is Zyte in default `browserHtml` mode and that an un-keyed deployment is a no-op falling through to the never-silently-miss hint
- [x] 3.4 Add/verify an orchestrator-level test that an SPA which raw-shells → browser-still-shells escalates to the paid tier (mocked Zyte) and installs the rendered result
- [x] 3.5 Run the P1 tests green

## 6. Escalate to a paid site render on a converted/walled failure (P4)

- [x] 6.1 Write failing tests: HN handler sets `escalate_to_render` on Algolia API non-2xx and on an unparseable body; leaves it unset on success
- [x] 6.2 Write failing orchestrator tests: a handler result with `escalate_to_render` (even verdict `not_found`) STOPS the free ladder (raw never runs) and renders via the paid tier on the ORIGINAL url; and a no-paid-key render fails loud (`retrieval_incomplete`), still skipping the free ladder
- [x] 6.3 Add the typed `escalate_to_render: bool = False` field to `TierResult` (no dict bag; documented) + `render_requested` on `FetchContext`
- [x] 6.4 Tier loop: on `escalate_to_render` record a diagnostic + non-authoritative observation, set `render_requested`, STOP the free ladder
- [x] 6.5 Gate/escalate phase: paid-render fast-path (dispatch Zyte on the original URL, skip own-browser); on render failure emit the critical `try_user_browser` hint; `build_response` forces `retrieval_incomplete` when a requested render failed
- [x] 6.6 Set `escalate_to_render` on the HN handler's converted-fetch failure paths (non-ok status + unparseable JSON)
- [x] 6.7 Reddit: a search/listing `403` escalates to a paid render (`_render_escalation_signal`) instead of the eager `_walled_signal`; thread 403 unchanged; update the affected reddit test
- [x] 6.8 Run the P4 tests green

## 4. Operational propagation

- [x] 4.1 Run `make install-global` to refresh the installed MCP binary with the current tree (Reddit `search.rss` handler + the new HN Algolia handler)
- [x] 4.2 Live-verify end-to-end in an MCP session: `hn.algolia.com/?q=…` returns real stories; a Reddit search URL returns real results; an unknown SPA either renders via Zyte or reports `retrieval_incomplete` (never a confident wrong answer)

## 5. Gate & finalize

- [x] 5.1 Run `make check` (lint + ty + test, coverage ≥85%) and fix any fallout
- [x] 5.2 Update `CHANGELOG.md` with the shipped behavior (HN Algolia search, obstacle-conditioned confidence, js_required paid render)
- [x] 5.3 Consider whether the output benchmark (`make bench`) should be run — this touches extraction/envelope + tier routing; run if the confidence/obstacle change could move clarity/conformance scores, and record findings under `eval/`
