## Why

The 2026-05-07 spike named two specific cases that broke WebFetch and burn agent tokens worst: Reddit threads (markdown gets truncated, comments lost) and Hacker News (article text + comment tree gets mangled). Both have official-ish JSON APIs that beat any scraping approach: Reddit's `<url>.json?limit=500&raw_json=1` returns the post + full comment tree in one shot, and HN's Algolia API returns recursive item trees with all kids. PR5 adds these as **tier-0 site handlers** — registered ahead of `raw` in `TIER_ORDER`, dispatched by URL match, returning fully-rendered markdown that bypasses trafilatura entirely. Two specific URLs go from "shrug and lose data" to "full thread + every comment in one fetch."

## What Changes

- Add `src/a2web/handlers/__init__.py` — re-exports plus a `match_handler(url) -> Tier | None` resolver consulted by the orchestrator before raw.
- Add `src/a2web/handlers/reddit.py` — `RedditHandler` matching `*.reddit.com/r/*/comments/*` (and equivalent shortlinks). Fetches `<url>.json?limit=500&raw_json=1` with the default Safari UA via `httpx`. Recursive walk over the comment tree → markdown with depth-based `>` quoting. Tier name reports as `site_handler:reddit`.
- Add `src/a2web/handlers/hn.py` — `HNHandler` matching `news.ycombinator.com/item?id=<n>`. Extracts the item id, hits `https://hn.algolia.com/api/v1/items/<id>` (no auth), recursive walker over `kids` → markdown. Tier name reports as `site_handler:hn`.
- Update `src/a2web/tiers/__init__.py` — `TIER_ORDER` becomes `("site_handler", "raw")`; the new `"site_handler"` slot dispatches via `match_handler(url)` to the right handler. If no handler matches, the tier returns a sentinel `Verdict.other` with a tier_extras flag that the orchestrator interprets as "skip silently, no diagnostic row."
- Extend the `TierResult` contract: handlers populate `tier_extras["pre_rendered"]` with `{"content_md": str, "title": str | None, "byline": str | None, "headings": list[Heading]}`. The orchestrator checks for this and **skips extraction** when present; the gate still runs on the rendered markdown.
- Update `src/a2web/fetcher.py`:
  - Add a "skip silent" sentinel path so site_handler returning "no match" doesn't pollute the `diagnostics` list.
  - If `tier_result.tier_extras.get("pre_rendered")` is set, use it instead of running trafilatura/htmldate/metadata/selectolax. The gate runs on `content_md`; cache write proceeds with the original JSON response body (so future cache hits re-render? — see Decision 5).
- Add `httpx>=0.27,<1` to dependencies (already declared) — handlers use `httpx.AsyncClient` rather than `curl_cffi`; these APIs don't need TLS impersonation.
- Tests: handler URL matching (positive + negative), Reddit JSON → markdown rendering against a fixture, HN Algolia tree → markdown rendering against a fixture, `match_handler` returning `None` for non-matching URLs, fetcher integration that a Reddit URL routes to the handler and produces real markdown without invoking trafilatura.
- README quick-start gets a Reddit/HN call example.

## Capabilities

### New Capabilities

- `site-handlers`: `match_handler(url)` resolver + per-host handlers (Reddit, HN in PR5). Tier-0 dispatch, JSON-API-backed, pre-rendered markdown.

### Modified Capabilities

- `tier-pipeline`: `TIER_ORDER` becomes `("site_handler", "raw")`; the protocol gains an optional `pre_rendered` extra in `TierResult.tier_extras` that the orchestrator honors by skipping the trafilatura/htmldate/metadata phase. A "no match" return path on the site_handler tier does not produce a diagnostic row (silent skip).
- `app-composition`: Reddit and HN URLs now produce real markdown via the handler path. Tool signature unchanged; envelope payload becomes much richer for these hosts.

## Impact

- **Code**: 3 new files in `src/a2web/handlers/`, ~250–350 LOC for the two handlers + dispatcher.
- **Public surface**: `match_handler(url)` is consumed only by the orchestrator. Adding more handlers in PR8 means dropping a new file under `handlers/` and registering it.
- **Dependencies**: `httpx` is already declared; no new top-level deps.
- **Performance**: Reddit/HN fetches now do one HTTP call against an official endpoint instead of a JS-rendered scrape. Typical Reddit thread (~300 comments) returns in ~500–800 ms; markdown rendering adds <50 ms.
- **Cache invariants**: handlers cache the JSON response body (not the rendered markdown) so a future cache rewrite that includes the rendering pipeline can re-render from the cached JSON. Block pages still NEVER enter the cache.
- **No new lifespan**: handlers use a per-call `httpx.AsyncClient` (cheap, no warmup). PR7 will introduce a shared client when the proxy pool lands.
- **Operator privacy**: Reddit + HN URLs in the log already include the post id and subreddit/HN item; no new exposure.
