# site-handlers Specification

## Purpose
TBD - created by archiving change pr5-site-handlers. Update Purpose after archive.
## Requirements
### Requirement: match_handler resolver

The system SHALL expose `match_handler(url: str) -> Tier | None` in `a2web.handlers.__init__`. The resolver SHALL iterate registered handlers in declaration order and return the first whose `matches(url)` returns `True`. Returning `None` is the normal "no handler applies" outcome.

#### Scenario: Resolver returns None for unmatched URL

- **WHEN** `match_handler("https://example.com/post")` is called
- **THEN** the return value is `None`

#### Scenario: Resolver returns the matching handler

- **WHEN** `match_handler("https://www.reddit.com/r/x/comments/abc/title")` is called
- **THEN** the return value is an instance of `RedditHandler`

### Requirement: Reddit handler

The system SHALL provide `RedditHandler` in `a2web.handlers.reddit` with `name = "site_handler:reddit"`. `matches(url)` SHALL return `True` for URLs whose host is `reddit.com`, `www.reddit.com`, or `old.reddit.com`, and whose path matches `/r/<sub>/comments/<id>...`. The handler SHALL fetch `<url>.json?limit=500&raw_json=1` via `httpx`, parse the response, and produce markdown comprising the post body followed by every comment depth-quoted with `>` prefixes.

The handler SHALL populate `TierResult.tier_extras["pre_rendered"]` with `content_md`, `title`, `byline`, and `headings`. The `body` field SHALL contain the original JSON response bytes (for cache + future replay) with `content_type = "application/json"`.

#### Scenario: Comment URL matches

- **WHEN** `RedditHandler().matches("https://www.reddit.com/r/LocalLLaMA/comments/abc/title/")` is called
- **THEN** the return value is `True`

#### Scenario: JSON tree renders to depth-quoted markdown

- **WHEN** the handler fetches a fixture JSON containing a post with two top-level comments and one nested reply
- **THEN** the rendered `content_md` includes the post title as `# <title>`, the post body, and three quoted comment blocks with depth-correct `>` prefixes (`>` for top-level, `>>` for nested)

#### Scenario: HTTP failure returns a verdict, not an exception

- **WHEN** the upstream `.json` endpoint returns 403 or times out
- **THEN** the handler returns a `TierResult` with `verdict in {Verdict.connection_error, Verdict.timeout}` and the orchestrator falls through to the raw tier

### Requirement: Hacker News handler

The system SHALL provide `HNHandler` in `a2web.handlers.hn` with `name = "site_handler:hn"`. `matches(url)` SHALL return `True` for URLs of the form `https://news.ycombinator.com/item?id=<n>`. The handler SHALL fetch `https://hn.algolia.com/api/v1/items/<n>` via `httpx` and produce markdown containing the item's text/title followed by every reply in the `kids` tree, depth-quoted.

The handler SHALL populate `TierResult.tier_extras["pre_rendered"]` and set `body` to the JSON response with `content_type = "application/json"`.

#### Scenario: Item URL matches

- **WHEN** `HNHandler().matches("https://news.ycombinator.com/item?id=12345")` is called
- **THEN** the return value is `True`

#### Scenario: Algolia tree renders to depth-quoted markdown

- **WHEN** the handler fetches a fixture JSON for an item with two kids, one of which has its own kid
- **THEN** the rendered `content_md` includes the item title (or a story header), the item text, and three quoted reply blocks with depth-correct `>` prefixes

### Requirement: Handlers MUST NOT raise on routine HTTP failures

Both `RedditHandler` and `HNHandler` SHALL translate connection / TLS / timeout / 4xx / 5xx outcomes into closed-enum `Verdict` values exactly as `RawTier` does. Exceptions SHALL NOT propagate to the orchestrator.

#### Scenario: Timeout maps to Verdict.timeout

- **WHEN** the handler's HTTP call exceeds the timeout
- **THEN** the returned `TierResult.verdict == Verdict.timeout` and no exception propagates

### Requirement: arxiv handler renders abs page from export API

The system SHALL provide `ArxivHandler` matching URLs of the form `https?://arxiv.org/abs/<id>` (case-insensitive). The handler SHALL fetch `https://export.arxiv.org/api/query?id_list=<id>`, parse the Atom XML with `xml.etree.ElementTree`, and populate `tier_extras["pre_rendered"]` with `content_md` (abstract), `title` (entry title, whitespace-collapsed), `byline` (comma-joined author names), and `headings` (top-level title + `## Categories`).

#### Scenario: Valid arxiv id returns rendered abstract

- **WHEN** the URL is `https://arxiv.org/abs/2401.12345` and the export API returns a valid Atom feed with one entry
- **THEN** the handler returns `verdict == Verdict.ok` and `pre_rendered.title` matches the entry title

#### Scenario: Invalid id returns not_found

- **WHEN** the export API returns an Atom feed with zero entries (arxiv's behavior for unknown ids)
- **THEN** the handler returns `verdict == Verdict.not_found`

### Requirement: wikipedia handler renders Parsoid HTML

The system SHALL provide `WikipediaHandler` matching URLs of the form `https?://<lang>.wikipedia.org/wiki/<title>` where `<lang>` is a 2–3 letter ISO code. The handler SHALL fetch `https://<lang>.wikipedia.org/api/rest_v1/page/html/<title>` and run trafilatura on the response to produce markdown. `pre_rendered.title` SHALL come from the URL slug (URL-decoded, underscores → spaces).

#### Scenario: English article renders cleanly

- **WHEN** the URL is `https://en.wikipedia.org/wiki/Octopus`
- **THEN** the handler dispatches the REST API and returns a `pre_rendered.content_md` non-empty string with `title == "Octopus"`

#### Scenario: Non-English language code respected

- **WHEN** the URL is `https://ru.wikipedia.org/wiki/Москва`
- **THEN** the REST API call uses `ru.wikipedia.org` (not `en.`)

### Requirement: github handler renders repo / issue / pull URLs

The system SHALL provide `GitHubHandler` matching three URL shapes:

- `github.com/<owner>/<repo>` (and trailing slash variants)
- `github.com/<owner>/<repo>/issues/<n>`
- `github.com/<owner>/<repo>/pull/<n>`

For each shape it SHALL call the corresponding GitHub REST API endpoint(s) and produce `pre_rendered.content_md`. When `settings.github_token` is non-empty, requests SHALL carry `Authorization: Bearer <token>`; otherwise unauthenticated.

#### Scenario: Repo URL returns metadata + README

- **WHEN** the URL is `https://github.com/octocat/Hello-World`
- **THEN** the handler calls both `/repos/octocat/Hello-World` and `/repos/octocat/Hello-World/readme`, decodes the base64 README content, and returns `pre_rendered.content_md` with the repo description, stars/forks/language, then the README body

#### Scenario: Issue URL returns issue + threaded comments

- **WHEN** the URL is `https://github.com/octocat/Hello-World/issues/42`
- **THEN** the handler calls `/repos/octocat/Hello-World/issues/42` and its `/comments` endpoint, and renders title + body + comments in chronological order

#### Scenario: Pull URL returns PR + reviews + comments

- **WHEN** the URL is `https://github.com/octocat/Hello-World/pull/7`
- **THEN** the handler calls the pulls endpoint, the reviews endpoint, and the comments endpoint, and renders all three sections

#### Scenario: 429 rate limit surfaces as rate_limited verdict

- **WHEN** any GitHub API call returns 429 (or 403 with `X-RateLimit-Remaining: 0`)
- **THEN** the handler returns `verdict == Verdict.rate_limited`; operator hint mentions `A2WEB_GITHUB_TOKEN` to raise the limit

#### Scenario: Token absence does not block unauthenticated calls

- **WHEN** `settings.github_token` is `""`
- **THEN** the handler issues requests without an `Authorization` header and otherwise behaves identically (subject to the 60 req/hr unauthenticated limit)

### Requirement: HN front page renders both article and discussion URLs

For each external-link story on the Hacker News front page, the `HNHandler` SHALL emit, in `content_md`, both the article URL and the story's Hacker News discussion URL (`https://news.ycombinator.com/item?id=<objectID>`). For text-only stories (no external URL), the discussion URL SHALL be the single URL emitted. The `next_links` array SHALL carry one `NextLink` per story (the article URL for external-link stories, the discussion URL for text-only stories) — it SHALL NOT emit a second `NextLink` for the discussion URL.

#### Scenario: external-link story exposes both URLs in content

- **WHEN** the HN handler renders a front-page fixture containing an external-link story
- **THEN** that story's line in `content_md` contains both the external article URL and the `https://news.ycombinator.com/item?id=<objectID>` discussion URL

#### Scenario: text-only story exposes the discussion URL

- **WHEN** the HN handler renders a front-page fixture containing a text-only story (no `url` field)
- **THEN** that story's line in `content_md` contains the `https://news.ycombinator.com/item?id=<objectID>` discussion URL

#### Scenario: next_links stays one entry per story

- **WHEN** the HN handler renders a front-page fixture with N external-link stories
- **THEN** `next_links` contains at most one `NextLink` per story and no discussion-URL duplicate entry

### Requirement: TierResult carries next_links

The `TierResult` dataclass SHALL gain a typed field `next_links: list[NextLink]` with default `field(default_factory=list)`. Handlers SHALL populate this field on listing-style URLs from their already-parsed structured response (no extra HTTP call, no extra parse pass). The orchestrator SHALL thread the handler-supplied list into the final `FetchResponse.next_links` (subject to the Tier 2 re-ranking rule in `link-discovery` when `ask=` is set).

#### Scenario: Handler returns empty list when no drilldown layer exists

- **WHEN** a handler runs on a permalink-style URL (e.g. a single Reddit thread, a single arXiv abstract)
- **THEN** the returned `TierResult.next_links` is `[]` (empty list, not absent)

### Requirement: Reddit listing handler matches and populates candidates

The `RedditHandler` SHALL extend `matches(url)` to additionally return `True` for subreddit-listing URLs of the form `/r/<sub>/` and `/r/<sub>/{hot,new,top,rising}/` (in addition to the existing `/r/<sub>/comments/<id>...` permalink pattern). On a listing URL the handler SHALL fetch `<url>.json?limit=25&raw_json=1`, parse the response, and populate `TierResult.next_links` with the top 10 permalinks sorted by the listing's natural order, each entry built as:

- `anchor` — the post `title` (truncated to 120 chars if longer)
- `url` — the post's full permalink (`https://www.reddit.com/r/<sub>/comments/<id>/...`)
- `reason` — `f"{score} score, {num_comments} comments"`
- `kind` — `"drilldown"`

Posts with `over_18 == true` SHALL be skipped from the candidate list when the listing URL itself is not an NSFW subreddit (i.e. the originally requested subreddit's `over18` flag is `false`).

#### Scenario: Subreddit listing matches

- **WHEN** `RedditHandler().matches("https://www.reddit.com/r/LocalLLaMA/")` is called
- **THEN** the return value is `True`

#### Scenario: Listing populates top 10 candidates

- **WHEN** the handler fetches a fixture listing JSON with 25 children of varying scores
- **THEN** `TierResult.next_links` contains exactly 10 entries, each with `kind == "drilldown"` and `reason` matching the `<score> score, <num_comments> comments` pattern

#### Scenario: Permalink URL still returns empty candidates

- **WHEN** the handler runs on `https://www.reddit.com/r/LocalLLaMA/comments/abc/title/`
- **THEN** `TierResult.next_links == []`

#### Scenario: NSFW posts filtered when listing is SFW

- **WHEN** the handler runs on a fixture SFW-subreddit listing where 3 of the top-by-score posts have `over_18 == true`
- **THEN** those 3 are skipped and the candidate list comprises the next 10 non-NSFW posts

### Requirement: HN front page handler matches and populates candidates

The `HNHandler` SHALL extend `matches(url)` to additionally return `True` for `https://news.ycombinator.com/` and `https://news.ycombinator.com/news` (front page variants). On a front-page URL the handler SHALL fetch `https://hn.algolia.com/api/v1/search?tags=front_page` and populate `TierResult.next_links` with up to 10 entries. For each story, the handler SHALL emit ONE candidate:

- If the story has an external `url`, the candidate SHALL point to that `url` with `kind="drilldown"` and `reason = f"{points} points, {num_comments} comments"`
- If the story is text-only (`url` absent), the candidate SHALL point to `https://news.ycombinator.com/item?id=<n>` with `kind="drilldown"` and the same `reason` shape

#### Scenario: Front page matches

- **WHEN** `HNHandler().matches("https://news.ycombinator.com/")` is called
- **THEN** the return value is `True`

#### Scenario: External-link story produces drilldown to external URL

- **WHEN** the handler processes a front-page Algolia result with a non-null `url` field
- **THEN** the corresponding candidate has `url` set to the external URL and `kind == "drilldown"`

#### Scenario: Item URL still returns empty candidates

- **WHEN** the handler runs on `https://news.ycombinator.com/item?id=12345`
- **THEN** `TierResult.next_links == []`

### Requirement: arXiv listing handler matches and populates candidates

An `ArxivHandler` SHALL extend `matches(url)` to additionally return `True` for category-listing URLs of the form `https?://arxiv.org/list/<cat>/<yymm>` and `https?://arxiv.org/list/<cat>/recent`. On a listing URL the handler SHALL fetch the listing HTML, parse the entries, and populate `TierResult.next_links` with up to 10 abs-page links, each built as:

- `anchor` — the paper title (truncated to 120 chars if longer)
- `url` — `https://arxiv.org/abs/<id>`
- `reason` — comma-joined author surnames (truncated to 80 chars)
- `kind` — `"drilldown"`

#### Scenario: Category listing matches

- **WHEN** `ArxivHandler().matches("https://arxiv.org/list/cs.LG/2401")` is called
- **THEN** the return value is `True`

#### Scenario: Listing populates abs candidates

- **WHEN** the handler parses a fixture listing page with 15 entries
- **THEN** `TierResult.next_links` contains exactly 10 entries, each with `kind == "drilldown"` and `url` matching `https://arxiv.org/abs/<id>`

#### Scenario: Single abs URL still returns empty candidates

- **WHEN** the handler runs on `https://arxiv.org/abs/2401.12345`
- **THEN** `TierResult.next_links == []`

### Requirement: GitHub repo handler populates issue/pull candidates

The `GitHubHandler` SHALL populate `TierResult.next_links` on a repo URL (`github.com/<owner>/<repo>` with no further path segments). The candidates SHALL include up to 5 top open issues and up to 5 top open pull requests, each as:

- `anchor` — the issue or PR title
- `url` — the full GitHub URL (`https://github.com/<owner>/<repo>/issues/<n>` or `/pull/<n>`)
- `reason` — `f"issue · {comments} comments"` for issues, `f"PR · {comments} comments"` for pulls
- `kind` — `"related"` (peers of the repo's main content, not deeper layers)

Issue and PR URLs (terminal pages) SHALL return `next_links == []`.

#### Scenario: Repo URL populates issue + PR candidates

- **WHEN** the handler runs on `https://github.com/octocat/Hello-World`
- **THEN** the candidate list contains up to 10 entries split between `/issues/<n>` and `/pull/<n>` URLs, each with `kind == "related"`

#### Scenario: Issue URL returns empty candidates

- **WHEN** the handler runs on `https://github.com/octocat/Hello-World/issues/42`
- **THEN** `TierResult.next_links == []`

### Requirement: Wikipedia handler emits outbound article links as related candidates

The `WikipediaHandler` SHALL populate `TierResult.next_links` with up to 10 outbound `wikilinks` (links to other articles on the same language Wikipedia) parsed from the Parsoid HTML response. Each candidate SHALL be:

- `anchor` — the link's visible text
- `url` — the full article URL (`https://<lang>.wikipedia.org/wiki/<target>`)
- `reason` — `"related article"` (one short phrase; no per-link signal available without an extra fetch)
- `kind` — `"related"`

External citation links (footnote `[1]`, `[2]`, etc. pointing to non-Wikipedia hosts) SHALL be omitted from the candidate list in v1 — they belong to `kind="source"` and are deferred to a later change.

#### Scenario: Article page populates wikilinks

- **WHEN** the handler runs on `https://en.wikipedia.org/wiki/Octopus`
- **THEN** the candidate list contains up to 10 entries, each with `kind == "related"` and `url` matching `https://en.wikipedia.org/wiki/.+`

#### Scenario: All candidates stay on the source language wiki

- **WHEN** the handler runs on `https://ru.wikipedia.org/wiki/Москва`
- **THEN** every candidate URL's host is `ru.wikipedia.org`

### Requirement: no_match is reserved for URLs no handler claims

A result dispatched through `SiteHandlerTier` SHALL set `no_match` (or `skipped`) on its `TierResult` ONLY to mean "no registered handler claims this URL." A handler that DOES claim a URL — its `matches(url)` returned `True` — but fails to retrieve usable content SHALL return a real closed-enum `Verdict` observation, never `no_match`. This covers, in particular: an upstream soft-block (an HTTP 200 carrying a throttle or error body, e.g. Reddit's `{"error": 429}`), an empty listing, and a deleted or removed thread. A matched-but-failed handler result SHALL produce an observation / diagnostic row in the cascade log; only a genuine no-handler-claims outcome is silently skipped.

#### Scenario: Reddit soft-block surfaces as a real verdict

- **WHEN** the Reddit handler claims a listing URL and the `.json` endpoint returns HTTP 200 with a throttle body (e.g. `{"error": 429}` or an empty listing payload)
- **THEN** the handler returns a `TierResult` with a real verdict (`rate_limited` for a throttle body), not `no_match`, and the cascade records an observation for the site-handler step

#### Scenario: Unclaimed URL is the only silent skip

- **WHEN** no registered handler's `matches(url)` returns `True`
- **THEN** `SiteHandlerTier` returns `no_match`, and the cascade records no observation / diagnostic row for the site-handler step

### Requirement: Site handlers receive resolved cookies

The `SiteHandlerTier` dispatch seam SHALL thread the per-fetch resolved cookies into the handler. `Handler.fetch` SHALL accept the resolved cookie set, and a handler that issues authenticated-capable requests (for example the Reddit handler's `.json` call) SHALL attach those cookies to its HTTP client. When `cookie_source == "none"` or no cookies are resolved for the request host, handlers SHALL behave exactly as before — unauthenticated, no behavior change.

#### Scenario: Reddit handler attaches resolved cookies

- **WHEN** a fetch resolves Reddit session cookies for the host and dispatches the Reddit handler
- **THEN** the handler's `.json` HTTP request carries those cookies

#### Scenario: No cookies resolved leaves handler behavior unchanged

- **WHEN** `cookie_source == "none"`, or the cookie jar resolves no cookies for the host
- **THEN** handlers issue unauthenticated requests exactly as before

