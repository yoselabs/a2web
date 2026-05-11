## MODIFIED Requirements

### Requirement: Reddit handler

Behavior preserved from v0.1.0. The handler SHALL populate the *typed* `TierResult.pre_rendered: Rendered | None` field (not `tier_extras["pre_rendered"]: dict`) with `content_md`, `title`, `byline`, `headings`. `body` remains the original JSON response bytes; `content_type = "application/json"`.

#### Scenario: Comment URL matches

- **WHEN** `RedditHandler().matches("https://www.reddit.com/r/LocalLLaMA/comments/abc/title/")` is called
- **THEN** the return value is `True`

#### Scenario: Pre-rendered typed field populated

- **WHEN** the handler fetches a fixture JSON containing a post with two top-level comments and one nested reply
- **THEN** `tier_result.pre_rendered` is a `Rendered` instance whose `content_md` includes the post title as `# <title>`, the post body, and three quoted comment blocks with depth-correct `>` prefixes

#### Scenario: HTTP failure returns a verdict, not an exception

- **WHEN** the upstream `.json` endpoint returns 403 or times out
- **THEN** the handler returns a `TierResult` with `verdict in {Verdict.connection_error, Verdict.timeout}` and the orchestrator falls through to the raw tier

### Requirement: Hacker News handler

Behavior preserved from v0.1.0. The handler SHALL populate the typed `TierResult.pre_rendered: Rendered | None` field with `content_md`, `title`, `byline`, `headings` (replacing the `tier_extras["pre_rendered"]: dict` bag). `body` SHALL remain the original JSON response bytes; `content_type` SHALL equal `"application/json"`.

#### Scenario: Item URL matches

- **WHEN** `HNHandler().matches("https://news.ycombinator.com/item?id=12345")` is called
- **THEN** the return value is `True`

#### Scenario: Pre-rendered typed field populated for HN tree

- **WHEN** the handler fetches a fixture JSON for an item with two kids, one of which has its own kid
- **THEN** `tier_result.pre_rendered.content_md` includes the item title, the item text, and three quoted reply blocks with depth-correct `>` prefixes

### Requirement: arxiv handler renders abs page from export API

Behavior preserved from v0.1.0. The handler SHALL populate the typed `TierResult.pre_rendered: Rendered | None` field with `content_md` (abstract), `title` (whitespace-collapsed entry title), `byline` (comma-joined authors), `headings` (top-level title + `## Categories`). The `tier_extras` dict bag MUST NOT be used.

#### Scenario: Valid arxiv id returns rendered abstract

- **WHEN** `ArxivHandler` fetches `https://arxiv.org/abs/2401.12345` against a fixture
- **THEN** `tier_result.pre_rendered.content_md` is the abstract, `tier_result.pre_rendered.title` is whitespace-collapsed, `tier_result.pre_rendered.byline` is comma-joined authors

### Requirement: Wikipedia handler

Behavior preserved from v0.1.0. The handler SHALL populate the typed `TierResult.pre_rendered: Rendered | None` field rather than the `tier_extras` dict bag. Content extraction via the Wikipedia REST API + trafilatura SHALL be unchanged.

#### Scenario: Wikipedia URL renders to markdown

- **WHEN** `WikipediaHandler` fetches a fixture for a wikipedia article
- **THEN** `tier_result.pre_rendered.content_md` contains the article body in markdown, `tier_result.pre_rendered.title` matches the article title

### Requirement: GitHub handler

Behavior preserved from v0.1.0. The handler SHALL populate the typed `TierResult.pre_rendered: Rendered | None` field rather than the `tier_extras` dict bag. `A2WEB_GITHUB_TOKEN` env var support SHALL be preserved (raises rate limit 60/hr → 5000/hr when set).

#### Scenario: Repo URL renders to markdown

- **WHEN** `GitHubHandler` fetches a fixture for `https://github.com/owner/repo`
- **THEN** `tier_result.pre_rendered.content_md` contains the README content (or repo metadata when no README is available)

### Requirement: match_handler resolver

Contract preserved from v0.1.0. The system SHALL expose `match_handler(url: str) -> Tier | None` in `a2web.handlers.__init__`. The resolver SHALL iterate registered handlers in declaration order and return the first whose `matches(url)` returns `True`. Returning `None` SHALL be the normal "no handler applies" outcome.

#### Scenario: Resolver returns None for unmatched URL

- **WHEN** `match_handler("https://example.com/post")` is called
- **THEN** the return value is `None`

#### Scenario: Resolver returns the matching handler

- **WHEN** `match_handler("https://www.reddit.com/r/x/comments/abc/title")` is called
- **THEN** the return value is an instance of `RedditHandler`

### Requirement: Handlers MUST NOT raise on routine HTTP failures

Contract preserved from v0.1.0. All site handlers (Reddit, HN, arxiv, Wikipedia, GitHub) SHALL translate connection / TLS / timeout / 4xx / 5xx outcomes into closed-enum `Verdict` values exactly as `RawTier` does. Exceptions SHALL NOT propagate to the orchestrator.

#### Scenario: Timeout maps to Verdict.timeout

- **WHEN** any handler's HTTP call exceeds the timeout
- **THEN** the returned `TierResult.verdict == Verdict.timeout` and no exception propagates
