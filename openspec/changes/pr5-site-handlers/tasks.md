## 1. Handlers package — `src/a2web/handlers/`

- [x] 1.1 `src/a2web/handlers/__init__.py` — declare `_HANDLERS: tuple[Tier, ...]` (RedditHandler, HNHandler), expose `match_handler(url) -> Tier | None`
- [x] 1.2 Re-export `RedditHandler`, `HNHandler` from the package init for tests

## 2. Reddit handler — `src/a2web/handlers/reddit.py`

- [x] 2.1 Define `RedditHandler` with `name = "site_handler:reddit"`
- [x] 2.2 `def matches(self, url: str) -> bool` — regex match against `(www\.|old\.)?reddit\.com/r/[^/]+/comments/...`
- [x] 2.3 `async def fetch(self, url: str, *, state: AppState) -> TierResult`:
  - rewrite to JSON URL: append `.json?limit=500&raw_json=1` (handle existing query string)
  - fetch via `httpx.AsyncClient(timeout=10)` with `state.settings.default_ua`
  - map errors → closed Verdict
  - parse JSON, render via `_render_thread`
  - return TierResult with `body=<json bytes>`, `content_type="application/json"`, `tier_extras={"pre_rendered": {...}, "more_stubs": <count>}`
- [x] 2.4 `_render_thread(payload) -> dict` — produce `{content_md, title, byline, headings}`. Walks post + comment tree; depth-quotes with `>`; appends `— u/<author>` byline per comment; counts and skips `kind=more` stubs

## 3. HN handler — `src/a2web/handlers/hn.py`

- [x] 3.1 Define `HNHandler` with `name = "site_handler:hn"`
- [x] 3.2 `def matches(self, url: str) -> bool` — match `news.ycombinator.com/item?id=<digits>`
- [x] 3.3 `async def fetch(...)`:
  - extract id from URL query
  - fetch `https://hn.algolia.com/api/v1/items/<id>` via httpx
  - render via `_render_item`
  - return TierResult with body=json bytes, content_type=application/json, tier_extras["pre_rendered"]
- [x] 3.4 `_render_item(payload) -> dict` — recursive walker over `kids`, depth-quoted

## 4. Site handler tier dispatcher — `src/a2web/tiers/site_handler.py`

- [x] 4.1 Define `SiteHandlerTier` with `name = "site_handler"`
- [x] 4.2 `async def fetch(self, url: str, *, state: AppState) -> TierResult`:
  - call `match_handler(url)`; if None → return TierResult with `tier_extras["no_match"]=True`, verdict=other (sentinel)
  - else delegate to `handler.fetch(url, state=state)` and return that result

## 5. Tier registry update — `src/a2web/tiers/__init__.py`

- [x] 5.1 Update `TIER_ORDER` to `("site_handler", "raw")`
- [x] 5.2 Update `REGISTRY` to include `"site_handler": SiteHandlerTier()`
- [x] 5.3 Re-export `SiteHandlerTier`

## 6. Orchestrator updates — `src/a2web/fetcher.py`

- [x] 6.1 In the tier loop: when a tier returns `tier_extras.get("no_match")`, continue to next tier WITHOUT appending a diagnostic row
- [x] 6.2 After a successful tier returns: check for `tier_extras["pre_rendered"]`. If present, populate `content_md`, `title`, `byline`, `headings` from it and skip the trafilatura/htmldate/metadata phase entirely
- [x] 6.3 Confirm gate still runs on `content_md` for pre-rendered results
- [x] 6.4 Confirm cache write stores `body` (json bytes) with `content_type=application/json` for handler-produced results

## 7. Tests — fixtures

- [x] 7.1 `tests/fixtures/reddit_thread.json` — a small thread payload (2 top-level + 1 nested + 1 `more` stub)
- [x] 7.2 `tests/fixtures/hn_item.json` — an Algolia item with `kids` (2 children, 1 with its own child)

## 8. Tests — `tests/test_handlers.py`

- [x] 8.1 `match_handler` returns None for example.com
- [x] 8.2 `match_handler` returns RedditHandler for a comments URL
- [x] 8.3 `match_handler` returns HNHandler for an item URL
- [x] 8.4 `RedditHandler.matches` False for subreddit listing
- [x] 8.5 `HNHandler.matches` False for HN front page
- [x] 8.6 Reddit `_render_thread(fixture)` produces depth-quoted markdown with the post title as `# `, the post body, and `>` `>>` comment quoting
- [x] 8.7 HN `_render_item(fixture)` produces depth-quoted markdown for the comment tree

## 9. Tests — fetcher integration

- [x] 9.1 Mock the SiteHandlerTier with a stub returning fixture JSON + pre_rendered → fetcher returns FetchResponse with tier=`site_handler:reddit`, status=ok, content_md non-empty, no `extract` diagnostic row
- [x] 9.2 No-match URL → site_handler emits no diagnostic; first diagnostic is `raw`
- [x] 9.3 Pre-rendered short markdown → gate trips length_floor, no cache row
- [x] 9.4 Pre-rendered ok markdown → cache row exists with content_type=application/json

## 10. Quality gate

- [x] 10.1 `make lint` clean (ASYNC100/210/230)
- [x] 10.2 `make ty` clean
- [x] 10.3 `make test` green, coverage ≥85%
- [x] 10.4 `make check` clean

## 11. Smoke (network — manual, not in CI)

- [x] 11.1 `uv run a2web web fetch --url=https://news.ycombinator.com/item?id=...` returns a populated envelope with `tier=site_handler:hn`
- [x] 11.2 `uv run a2web web fetch --url=https://www.reddit.com/r/.../comments/...` returns a populated envelope with `tier=site_handler:reddit`

## 12. Docs + commit

- [x] 12.1 Update `CLAUDE.md`: handlers section under architecture; document the pre_rendered + no_match contract
- [x] 12.2 Update `README.md` with a Reddit/HN example call
- [x] 12.3 Single commit "PR5: Reddit + HN site handlers"
- [x] 12.4 Hand off to PR6 (fit_md + actions playbook + OTel skeleton + diagnostic event bus)
