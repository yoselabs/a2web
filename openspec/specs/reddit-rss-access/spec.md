# reddit-rss-access Specification

## Purpose
TBD - created by archiving change reddit-reachability-never-silent-miss. Update Purpose after archive.
## Requirements
### Requirement: Reddit URL-shape to RSS projection
The Reddit handler SHALL project `search`, `listing`, and `thread` (comments) URL shapes to their `.rss` (Atom) equivalent and fetch that instead of the Datadome-walled `.json` endpoint. All listing sorts SHALL project: the bare subreddit (and `hot`/`best`, Reddit's default sort) projects to the bare `/r/<sub>/.rss` feed, and the explicit sorts `top`, `new`, `rising`, `controversial` project to `/r/<sub>/<sort>.rss` (preserving the `?t=` time window for `top`/`controversial`). `search` and `thread` shapes project likewise. (Empirically verified live: the bare `.rss` feed IS the hot feed — the earlier assumption that `hot` had no feed equivalent was wrong.)

#### Scenario: Search URL projects to search.rss
- **WHEN** a `/r/<sub>/search/?q=...` URL is fetched
- **THEN** the handler requests `/r/<sub>/search.rss?q=...` and renders the Atom entries as search-result stubs (title, author, permalink)

#### Scenario: Thread URL projects to thread .rss with comment samples
- **WHEN** a `/r/<sub>/comments/<id>/...` URL is fetched
- **THEN** the handler requests the thread `.rss` and renders the post plus comment bodies and authors

#### Scenario: Hot / bare listing projects to the bare feed
- **WHEN** a bare `/r/<sub>/` (or `/r/<sub>/hot`) URL is fetched
- **THEN** the handler requests `/r/<sub>/.rss` (the default/hot feed) and renders the Atom entries as post stubs with drill-down `next_links`

### Requirement: RSS sample limits are surfaced, never implied complete
The handler SHALL treat RSS comment output as a **sample** (flat, recent-ordered, ~25 max, no scores) and SHALL NOT present it as a complete or top-ranked comment set.

#### Scenario: Large thread returns a sample
- **WHEN** a thread with hundreds of comments is fetched via RSS
- **THEN** the response carries the available sample and does not claim to contain all comments

### Requirement: RSS rate limiting is retryable, not terminal
The handler SHALL back off on Reddit RSS `429` responses and reuse `http_cache`; a `429` SHALL be treated as retryable. If retries are exhausted, the handler SHALL fail loud (retrieval-completeness contract), never return a silent empty result.

#### Scenario: Burst 429 backs off then caches
- **WHEN** repeated RSS requests to one host return `429`
- **THEN** the handler backs off and serves a cached result when available, otherwise reports a loud failure

