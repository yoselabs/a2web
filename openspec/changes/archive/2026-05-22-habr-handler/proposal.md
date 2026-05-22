## Why

Habr (habr.com) is a high-traffic RU/EN tech publication and a frequent fetch target. Its article pages are a Vue SPA: the article *body* is server-rendered (trafilatura recovers it), but the *comment thread* is client-rendered — the raw HTML carries only `tm-placeholder` skeletons. A raw-tier fetch therefore returns the article and silently loses the entire discussion, and the orchestrator never escalates to the browser tier because the article alone satisfies the gate.

A probe confirmed Habr exposes a clean internal JSON API — `kek/v2` — that returns both the full article and the full comment tree, no browser required. This is the same pattern the `reddit` and `hn` handlers already use: hit the site's JSON endpoints, render `pre_rendered`.

## What Changes

- **New `HabrHandler`** (Strategy + Registry tier-0 handler, alongside `reddit` / `hn` / `arxiv` / `wikipedia` / `github`). `matches()` claims Habr article URLs — `habr.com/{ru,en}/articles/<id>/`, `/companies/<slug>/articles/<id>/`, and the legacy `/post/<id>/` and `/company/<slug>/blog/<id>/` forms.
- The handler fetches two `kek/v2` endpoints in parallel — `articles/<id>/` (article) and `articles/<id>/comments/` (comment tree) — and populates `TierResult.pre_rendered` with `content_md` (article markdown + a threaded `## Discussion` section), `title`, `byline` (author), `headings`.
- The comment tree renders **threaded** — indentation by reply depth, each comment carrying its author. A failed comments fetch degrades to article-only, never raises (per the existing handler routine-failure contract).
- No browser tier, no new dependency.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `site-handlers`: adds the `HabrHandler` requirement — a new tier-0 handler matching Habr article URLs and rendering article + threaded comments from the `kek/v2` API.

## Impact

- New `src/a2web/handlers/habr.py`; registered in the handler registry / `match_handler` declaration order.
- No new dependencies — `curl_cffi` (HTTP) and `lxml` (parse `textHtml` / comment `message` HTML to markdown) are already present.
- The `kek/v2` API is undocumented (it backs Habr's own frontend and mobile apps) — a fragility risk in the same class as the `reddit` / `hn` JSON dependencies; isolated to one handler, and the handler's routine-failure contract degrades gracefully (falls through to the generic path) rather than raising.
