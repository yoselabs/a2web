## ADDED Requirements

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
