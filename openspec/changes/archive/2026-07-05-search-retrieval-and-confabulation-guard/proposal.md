## Why

Community-site search retrieval has two holes and one silent-failure class, all confirmed against live traffic on 2026-07-05:

- A request for the HN/Algolia search UI (`hn.algolia.com/?q=…`) matches no handler, falls to the generic ladder, renders as an SPA shell, and the extractor **confabulated** — it returned an unrelated Anthropic-policy answer with `confidence: high` and only `obstacle: empty` as a (contradicted, easy-to-miss) warning. Silent wrong content is worse than a clean error.
- The `ask` envelope's `confidence` is computed purely from `(verdict, len(content_md))` and **ignores the LLM's own `obstacle` signal**, so an "empty/blocked" page can still surface as high confidence.
- An unknown JS-shell SPA that survives the browser rung dies as `length_floor` because the paid last-resort planner never treats `length_floor` as a wall — even though the paid render tier (Zyte `browserHtml`) demonstrably renders these pages (HN SPA → 30 stories; old.reddit search → 22 real results).

(Reddit search itself is already solved in-tree via the `search.rss` Atom handler — live-verified, 26 real results — so no new Reddit work is needed; it only needs to reach the installed binary.)

## What Changes

- **HN Algolia search handler**: `HNHandler.matches()` also accepts `hn.algolia.com/?q=<query>`; `fetch()` routes it to `https://hn.algolia.com/api/v1/search?query=<q>&tags=story&hitsPerPage=30`, reusing the existing `_render_front_page` rendering and `_front_page_candidates` link discovery. Deterministic — no SPA render, no browser, no paid tier.
- **Confabulation guard (obstacle → confidence/status)**: on the `ask` path, when the extractor reports `obstacle ∈ {empty, blocked, paywalled, error}`, cap `confidence` to `low`; when `obstacle ∈ {empty, blocked}`, also set `retrieval_incomplete = true` and add a `retrieval_incomplete` operator hint. Complements the already-shipped `extraction_empty` guard, which only fires on a literally empty answer — this covers the *plausible-but-wrong* answer.
- **Paid-render escalation for SPA shells**: the paid last-resort planner rule additionally fires `EscalatePaid` when the gate verdict is `length_floor` **and** the block-detector subsystem is `js_required` (browser rung already spent, paid budget unspent). Spend stays scoped to genuine SPA shells, never bare short pages.
- **Escalate to a paid site render on a converted/walled failure**: a new typed `escalate_to_render` signal on `TierResult`. A handler sets it when its rewritten fetch fails (HN's `hn.algolia.com/?q=` → the Algolia API) **or** its surface is walled (Reddit search/listing behind a 403). The orchestrator records the failed attempt as a diagnostic, **stops the free ladder** (raw/jina get fooled — an SPA shell can exceed the 500-char length floor and pass the gate as `ok`; the HN shell is ~587 chars — and the own-browser proved unreliable on these pages), and renders the **original** URL directly via the paid tier (Zyte `browserHtml`, proven: 30 HN stories / 22 Reddit results). No paid key → the empty body falls through to the never-silently-miss hint (fail loud). Built generically; HN and Reddit are the first adopters. **BREAKING (internal, unshipped): replaces the earlier `escalate_to_ladder` fall-through, which dead-ended on the SPA shell.**
- **Operational**: `make install-global` propagates the current tree (Reddit `search.rss` handler + the new HN handler) to the globally-installed MCP binary, since source edits do not auto-propagate.

## Capabilities

### New Capabilities

_None._ All changes modify existing capability requirements.

### Modified Capabilities

- `site-handlers`: HN handler gains a third match/route shape — the `hn.algolia.com/?q=` Algolia search UI URL resolves via the Algolia search API.
- `ask-response`: `confidence` becomes a function of the extractor's `obstacle` signal, not only `(verdict, content length)`; an obstacle caps confidence and (for empty/blocked) flags retrieval as incomplete.
- `retrieval-completeness`: the never-silently-miss floor extends to the confabulation case — an `obstacle`-flagged `ask` answer is surfaced as retrieval-incomplete rather than a confident answer.
- `paid-fetch-tiers`: the paid last-resort trigger recognizes a post-browser `length_floor` + `js_required` SPA shell as a wall worth a paid render.
- `tier-pipeline`: a new `escalate_to_render` `TierResult` signal lets a handler ask the orchestrator to render the original URL directly via the paid tier (skipping the free ladder + own-browser) when its rewritten fetch fails or its surface is walled.
- `reddit-rss-access`: a Reddit search/listing 403 (RSS rate-limited/blocked) escalates to a paid site render instead of failing loud, since Zyte `browserHtml` reads the page.

## Impact

- **Code**: `src/a2web/handlers/hn.py` (match + route + render-escalate on API failure), `src/a2web/handlers/reddit.py` (search/listing 403 → render-escalate), `src/a2web/fetcher_response.py` / the ask-path projection (obstacle→confidence/status; note the ordering constraint — `obstacle` is produced in `_phase_extract_answer`, *after* `build_response`, so the reconciliation lives where `obstacle` reaches the wire, not in `build_response`; plus the render-requested-failed → `retrieval_incomplete` rule), `src/a2web/actions/playbook.py` (`_decide_paid_last_resort` trigger + the `_PAID_WALL_VERDICTS` companion set), `src/a2web/tiers/__init__.py` (`escalate_to_render` field on `TierResult`), `src/a2web/fetcher.py` (tier-loop stop + gate-phase paid-render fast-path + loud miss on render failure).
- **Wire contract**: `ask` responses may now carry `confidence: low` + `retrieval_incomplete: true` + a `retrieval_incomplete` operator hint where they previously carried `confidence: high`. This is a correctness tightening, not a shape change; no field is added or removed.
- **Cost**: paid (Zyte) egress can now fire on `js_required` SPA shells that exhaust the browser rung — bounded by the existing single-paid-dispatch cap and gated on the `js_required` subsystem so it never triggers on generic short pages. HN Algolia search *removes* cost (API GET instead of a browser render).
- **Dependencies**: none added.
- **Ops**: the global MCP binary must be reinstalled to pick up the already-landed Reddit `search.rss` handler and the new HN handler.
