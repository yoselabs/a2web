## Why

PR5 shipped two handlers (Reddit, HN) that demonstrate the tier-0 pattern: when a URL matches a known site whose public API returns cleaner data than its HTML, dispatch directly to that API instead of running the full cascade. CLAUDE.md and the v0.1-design doc list six more candidates; PR8 ships the three with clean, unauthenticated public APIs (**arxiv, wikipedia, github**) and explicitly defers the three that don't (youtube, substack, twitter). Each new handler removes a class of fetches from the proxy/browser path entirely — arxiv abs pages render perfectly through their export API, Wikipedia REST returns trafilatura-clean HTML for any article, and GitHub's REST API turns issue/PR/repo URLs into structured JSON instead of JS-heavy client-rendered HTML.

## What Changes

- **`handlers/arxiv.py`** — `ArxivHandler`. Match: `arxiv.org/abs/<id>` (and `arxiv.org/pdf/<id>` post-rewrite from PR7b's playbook). API: `https://export.arxiv.org/api/query?id_list=<id>` (Atom XML) for canonical title/abstract/authors; falls back to scraping the `<meta>` tags on the abs page if the API call fails. Pre-rendered markdown carries title, authors as byline, abstract as content_md, plus a `## Categories` section. ~120 LOC.

- **`handlers/wikipedia.py`** — `WikipediaHandler`. Match: `*.wikipedia.org/wiki/<title>` (any language code). API: `https://<lang>.wikipedia.org/api/rest_v1/page/html/<title>` returns Parsoid-cleaned HTML — much smaller than the live page, no nav/sidebar/edit links. Hand to trafilatura inside the handler for markdown conversion. Pre-rendered title from the URL slug; first `<h1>` becomes content title. ~80 LOC.

- **`handlers/github.py`** — `GitHubHandler`. Match: three URL shapes:
  - `github.com/<owner>/<repo>` → `GET /repos/{owner}/{repo}` → README + repo metadata
  - `github.com/<owner>/<repo>/issues/<n>` → `GET /repos/{owner}/{repo}/issues/{n}` + comments
  - `github.com/<owner>/<repo>/pull/<n>` → `GET /repos/{owner}/{repo}/pulls/{n}` + reviews + comments
  
  All unauthenticated by default (60 req/hr per IP per GitHub policy). When `A2WEB_GITHUB_TOKEN` is set, send `Authorization: Bearer <token>` for the 5000 req/hr limit. README handler also fetches `GET /repos/{owner}/{repo}/readme` and decodes the base64 content. Pre-rendered markdown structured as `# repo` → metadata table → README body, OR `# Issue #N: title` → body → comments thread. ~180 LOC.

- **`handlers/__init__.py`** — register the three new handlers in `_HANDLERS`. Order matters for `match_handler`: most-specific first (none of the new three overlap, so append-order is fine).

- **`settings.py`** — add `github_token: str = ""` (env-only secret like `jina_key`; never written to YAML). No other settings changes — the API endpoints are hardcoded into each handler.

- **Tests** — one fixture file per handler with a recorded API response (offline-replay; no live network in CI). Cover happy path, 404, rate-limited (429), malformed JSON/XML. Reuse the existing handler-test pattern from `tests/test_handlers.py`.

## Capabilities

### Modified Capabilities

- `site-handlers` — adds three handlers (arxiv, wikipedia, github) to the existing tier-0 dispatch

## Impact

- `pyproject.toml`: no new deps (httpx already present; arxiv API XML is parsed with stdlib `xml.etree.ElementTree`)
- `src/a2web/handlers/arxiv.py`: new file, ~120 LOC
- `src/a2web/handlers/wikipedia.py`: new file, ~80 LOC
- `src/a2web/handlers/github.py`: new file, ~180 LOC
- `src/a2web/handlers/__init__.py`: 3 new entries in `_HANDLERS`, 3 new exports
- `src/a2web/settings.py`: 1 new field (`github_token`)
- Tests: 3 new files (~80 LOC each) + offline fixture JSON/XML files

## Out of Scope (deferred)

- **YouTube** — the watch page is JS-rendered; the transcript and metadata APIs need an OAuth flow or paid YouTube Data API key. Realistic options are (a) browser tier + transcript scrape, (b) `yt-dlp` as an optional dep. Defer to PR8b once browser-tier proxy plumbing (PR7e) lands so YT-via-browser is reliable.
- **Substack** — every Substack lives on a different domain (foo.substack.com or custom). Auto-detection means crawling the homepage for the Substack signature, which adds a handler-internal pre-fetch. Trafilatura already extracts Substack articles cleanly via the regular cascade; the handler win would be comments + paywall awareness, both better solved by archive escalation (PR7b) than a dedicated handler. Re-evaluate when archive coverage data shows specific gaps.
- **Twitter/X** — public API requires authenticated session; even Nitter mirrors are unstable. The honest answer for v0.1 is "X is not a supported site"; revisit when there's a clear cheap path.
- **Per-handler proxy plumbing** — PR7d wired raw + jina; handlers go through their own httpx clients. Threading proxy_url into each handler is mechanical but separate; defer to PR7e where browser/archive plumbing also lands.
