## Context

Probe results (curl_cffi, Chrome impersonation, anonymous):

- `GET habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru` → `200 application/json` — keys include `titleHtml`, `textHtml`, `author`, `statistics`, `hubs`, `flows`, `tags`, `timePublished`, `leadData`.
- `GET habr.com/kek/v2/articles/<id>/comments/?fl=ru&hl=ru` → `200 application/json` — keys `comments`, `threads`, `pinnedCommentIds`, `commentAccess`.

Both endpoints are open and unauthenticated. The article body arrives as `textHtml` (rendered HTML); comments arrive as a flat `comments` map plus a `threads` structure giving the reply tree.

`reddit.py` and `hn.py` establish the pattern: a tier-0 handler that calls a JSON endpoint and populates `TierResult.pre_rendered`, which the orchestrator uses directly (pre-rendered handler results bypass trafilatura).

## Goals / Non-Goals

**Goals:**
- Recover both the article and the full comment thread from a single, browser-free fetch.
- Render comments threaded, so "summarize the discussion" works.
- Degrade gracefully — a comments-endpoint failure still yields the article.

**Non-Goals:**
- Habr listing / hub pages (`habr.com/ru/articles/`, hub feeds) — out of scope; the generic detector or a later change covers feeds.
- Authenticated / paywalled corporate content — the handler fetches what the open API returns.

## Decisions

### D1 — API, not scraping or browser
The SPA's raw HTML has only `tm-placeholder` skeletons for comments. The `kek/v2` API is the only browser-free source of the discussion. Driving the browser tier purely to hydrate comments would cost seconds per fetch; the API is one round-trip.

### D2 — Parallel fetch of the two endpoints
Article and comments are independent GETs — fetch them concurrently in an `anyio` task group (the pattern `archive.py` already uses for its hedged Wayback / archive.ph fetches).

### D3 — Language parameter from the URL
The `kek/v2` endpoints take `?fl=&hl=` (feed-language / interface-language). Derive both from the URL's `/ru/` or `/en/` segment; default `ru` when absent.

### D4 — `matches()` covers the URL forms
A regex over Habr's article URL shapes: `/{ru,en}/articles/<id>/`, `/{ru,en}/companies/<slug>/articles/<id>/`, and the legacy `/{ru,en}/post/<id>/` and `/{ru,en}/company/<slug>/blog/<id>/`. The numeric `<id>` is what the API needs — the slug / company segments are cosmetic.

### D5 — Render: article + threaded discussion in one `content_md`
`titleHtml` + `textHtml` → markdown for the article body (`lxml` parse → markdown, same as other handlers). The `comments` + `threads` structure → a `## Discussion` section rendered **threaded**: indentation by reply depth, each comment prefixed with its author. `byline` = the article author; `headings` = the article title plus `## Discussion`.

### D6 — Routine-failure contract
Per the existing `Handlers MUST NOT raise on routine HTTP failures` requirement: a non-200 / malformed-JSON article response → `verdict == Verdict.not_found` (fall through to the generic path); a failed *comments* fetch → render the article alone, no discussion section, no raise.

## Risks / Trade-offs

- **Undocumented API drift** — `kek/v2` is Habr's internal frontend API → Mitigation: same risk class as the `reddit` / `hn` JSON dependencies; isolated to one handler; the routine-failure contract degrades to the generic path rather than raising. A handler test against a recorded fixture catches a shape change in CI.
- **Comment tree large on popular posts** → Mitigation: render is bounded the same way other handlers bound output; deep threads indent but the content is genuinely the discussion.

## Migration Plan

1. `handlers/habr.py` — `HabrHandler` with `matches()` + `fetch()`; register in `match_handler` order.
2. Recorded JSON fixtures (article + comments) for handler tests.
3. `make check` green.

No envelope change. Rollback: unregister the handler — Habr URLs fall back to the generic path (article only).

## Open Questions

- Whether to share the threaded-comment renderer with `structural-record-detection`'s depth-aware renderer — both render a reply tree to indented markdown. Defer until both have landed; refactor to a shared `packages/` helper if the duplication is real.
