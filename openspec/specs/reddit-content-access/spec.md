# reddit-content-access Specification

## Purpose
TBD - created by archiving change reddit-via-zyte. Update Purpose after archive.
## Requirements
### Requirement: Reddit URL normalization to the working channel
The Reddit handler SHALL normalize every Reddit URL shape it receives to the channel proven to return content: **thread/comments** URLs SHALL be rewritten to `https://old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top`, and **listing/search/subreddit** URLs to their new-reddit (shreddit) canonical form. Recognized thread inputs include `www`/`old`/`np`/`new` reddit hosts, `redd.it/<id>` short links, `/r/<sub>/s/<share>` share links, and `.json`/`.rss` suffixed variants. The handler SHALL NOT request the `.json` API endpoint (unreachable; ADR-0011).

#### Scenario: A new-reddit thread URL is routed to old.reddit
- **WHEN** an agent fetches `https://www.reddit.com/r/science/comments/6nz1k/title/`
- **THEN** the handler fetches `https://old.reddit.com/r/science/comments/6nz1k/title/?limit=500&sort=top`

#### Scenario: A share/short link is resolved then normalized
- **WHEN** an agent fetches a `redd.it/<id>` or `/r/<sub>/s/<share>` thread link
- **THEN** the handler resolves it to the canonical thread and fetches the old.reddit `?limit=500&sort=top` form

#### Scenario: A listing URL stays on new-reddit
- **WHEN** an agent fetches `https://www.reddit.com/r/gravelcycling/` or a search URL
- **THEN** the handler fetches the new-reddit canonical form, not old.reddit

### Requirement: Eager paid-tier fetch for Reddit
Because the free tier ladder (raw, jina, self-hosted browser without residential egress) provably fails on Reddit, the handler SHALL route Reddit fetches directly to the paid tier when one is available, rather than escalating through the free ladder. old.reddit content SHALL be fetched via the paid tier's raw (`httpResponseBody`) mode, since old.reddit is server-rendered.

#### Scenario: Reddit routes straight to the paid tier when keyed
- **WHEN** a Reddit URL is fetched and a paid tier (Zyte/Firecrawl) is configured
- **THEN** the handler dispatches the paid tier immediately without first attempting raw/jina/browser

#### Scenario: Un-keyed deployment falls back to RSS
- **WHEN** a Reddit URL is fetched and no paid tier is configured
- **THEN** the handler falls back to the keyless RSS channel (degraded sample), never to `.json`

### Requirement: old.reddit flat-HTML parsing to posts and comments
The handler SHALL parse old.reddit server-rendered HTML into structured post and comment data — author, score, body, and nesting depth per comment — without relying on shreddit web-components or generic article extraction.

#### Scenario: A thread yields structured scored comments
- **WHEN** an old.reddit thread page is fetched successfully
- **THEN** the response contains the post plus its comments with author, score, and nesting, as a scored sample (not flat/scoreless like RSS)

### Requirement: Availability-gated Reddit tier arbitration ladder
Reddit access SHALL be an availability-gated ladder in which no tier is hard-disabled; each rung participates only when its configuration and capability are present. Gated/logged-in content SHALL route to the self-hosted browser rung (only that rung can serve it). Public content SHALL be served by the first available rung in operator-configured policy order over `[self-hosted-browser, paid (Zyte/Firecrawl), RSS]`, and SHALL fail loud (never-silently-miss critical hint) when no rung can serve it.

#### Scenario: Policy order decides between free and paid for public reads
- **WHEN** both a self-hosted browser rung and a paid tier are available and the operator policy is cost/privacy-first
- **THEN** the self-hosted rung is used for public reads and the paid tier is the fallback

#### Scenario: Gated content requires the self-hosted rung
- **WHEN** logged-in/gated Reddit content is requested and no self-hosted browser rung is available
- **THEN** the fetch fails loud indicating a logged-in browser path is required, and does not silently return public-only or empty content

