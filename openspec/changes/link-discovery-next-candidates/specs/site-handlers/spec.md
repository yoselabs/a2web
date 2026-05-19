## ADDED Requirements

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
