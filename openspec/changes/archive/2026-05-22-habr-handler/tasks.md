## 1. Handler implementation

- [x] 1.1 New `src/a2web/handlers/habr.py` — `HabrHandler` with `matches(url)` covering the four Habr article URL forms (articles / companies-articles / legacy post / legacy company-blog), extracting the numeric id and language segment.
- [x] 1.2 Implement `fetch()` — parallel `anyio` task-group GETs of `kek/v2/articles/<id>/` and `kek/v2/articles/<id>/comments/` with `fl`/`hl` from the URL language; route through the raw HTTP client used by the other handlers.
- [x] 1.3 Render the article — `titleHtml` → `title`, `textHtml` → markdown body, `author` → `byline`.
- [x] 1.4 Render comments threaded — walk the `comments` / `threads` structure, emit a `## Discussion` section with reply-depth indentation and per-comment author.
- [x] 1.5 Routine-failure handling — article endpoint non-200 / bad JSON → `Verdict.not_found`; comments endpoint failure → article-only, no raise.
- [x] 1.6 Register `HabrHandler` in the handler registry / `match_handler` declaration order.

## 2. Tests

- [x] 2.1 Recorded JSON fixtures — one article response, one comments response (with a nested reply).
- [x] 2.2 Handler tests — article URL renders body + threaded `## Discussion`; comments-endpoint failure degrades to article-only without raising; unknown id → `not_found`; `/en/` vs `/ru/` selects `fl`/`hl`.
- [x] 2.3 `match_handler` resolves a Habr article URL to `HabrHandler`; a non-Habr URL does not.

## 3. Verify

- [x] 3.1 `make check` green — lint, `ty`, full suite, coverage ≥ 85%.
