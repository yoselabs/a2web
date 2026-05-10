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

#### Scenario: Subreddit listing does NOT match

- **WHEN** `RedditHandler().matches("https://www.reddit.com/r/LocalLLaMA/")` is called
- **THEN** the return value is `False` (PR5 covers comment threads only)

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

#### Scenario: Front page does NOT match

- **WHEN** `HNHandler().matches("https://news.ycombinator.com/")` is called
- **THEN** the return value is `False`

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

