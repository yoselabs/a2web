## MODIFIED Requirements

### Requirement: github handler renders repo / issue / pull URLs

The system SHALL provide `GitHubHandler` matching three URL shapes:

- `github.com/<owner>/<repo>` (and trailing slash variants)
- `github.com/<owner>/<repo>/issues/<n>`
- `github.com/<owner>/<repo>/pull/<n>`

For each shape it SHALL drive GitHub REST API calls through `gidgethub.sansio.GitHubAPI` over a curl_cffi-backed transport adapter, so every request inherits a2web's existing breakers / proxy routing / TLS-fingerprint behavior. It SHALL produce `pre_rendered.content_md` from the parsed responses. When `settings.github_token` is non-empty, requests SHALL carry `Authorization: Bearer <token>` (set via gidgethub's `oauth_token` parameter); otherwise unauthenticated.

The handler SHALL NOT introduce any GitHub HTTP traffic outside the curl_cffi tier — `gidgethub.aiohttp` / `gidgethub.httpx` / any other transport-owning gidgethub helper SHALL NOT be imported.

#### Scenario: Repo URL returns metadata + README

- **WHEN** the URL is `https://github.com/octocat/Hello-World`
- **THEN** the handler issues `/repos/octocat/Hello-World` and `/repos/octocat/Hello-World/readme` GitHub API calls via gidgethub through the curl_cffi adapter, and returns `pre_rendered.content_md` with the repo description, stars/forks/language, then the README body

#### Scenario: Issue URL returns issue + threaded comments

- **WHEN** the URL is `https://github.com/octocat/Hello-World/issues/42`
- **THEN** the handler issues `/repos/octocat/Hello-World/issues/42` and the comments iterator endpoint via gidgethub, and renders title + body + comments in chronological order

#### Scenario: Pull URL returns PR + reviews + comments

- **WHEN** the URL is `https://github.com/octocat/Hello-World/pull/7`
- **THEN** the handler issues the pulls endpoint, the reviews endpoint, and the comments endpoint via gidgethub, and renders all three sections

#### Scenario: 429 / rate-limit headers surface as rate_limited verdict

- **WHEN** any GitHub API call raises `gidgethub.RateLimitExceeded` (gidgethub maps both 429 and 403 + `X-RateLimit-Remaining: 0` to this exception)
- **THEN** the handler returns `verdict == Verdict.rate_limited` and the operator hint mentions `A2WEB_GITHUB_TOKEN` to raise the limit

#### Scenario: Token absence does not block unauthenticated calls

- **WHEN** `settings.github_token` is `""`
- **THEN** the handler constructs `GitHubAPI(oauth_token=None)` and otherwise behaves identically (subject to the 60 req/hr unauthenticated limit)

#### Scenario: All GitHub traffic flows through the curl_cffi adapter

- **WHEN** the handler executes any of the three URL shapes
- **THEN** every outbound HTTP request to `api.github.com` is dispatched through the curl_cffi session (so breakers, proxy routing, and TLS-fingerprint apply) — no socket is opened directly by gidgethub or its bundled helpers

### Requirement: GitHub repo handler populates issue/pull candidates

The `GitHubHandler` SHALL populate `TierResult.next_links` on a repo URL (`github.com/<owner>/<repo>` with no further path segments). The candidates SHALL include up to 5 top open issues and up to 5 top open pull requests, each as:

- `anchor` — the issue or PR title
- `url` — the full GitHub URL (`https://github.com/<owner>/<repo>/issues/<n>` or `/pull/<n>`)
- `reason` — `f"issue · {comments} comments"` for issues, `f"PR · {comments} comments"` for pulls
- `kind` — `"related"` (peers of the repo's main content, not deeper layers)

These candidates SHALL be sourced from a single `gidgethub` `getiter` call per shape with `per_page=5, sort=updated, state=open`; the handler SHALL NOT page beyond the first batch. Issue and PR URLs (terminal pages) SHALL return `next_links == []`.

#### Scenario: Repo URL populates issue + PR candidates

- **WHEN** the handler runs on `https://github.com/octocat/Hello-World`
- **THEN** the candidate list contains up to 10 entries split between `/issues/<n>` and `/pull/<n>` URLs, each with `kind == "related"`, sourced from one issues `getiter` and one pulls `getiter`

#### Scenario: Issue URL returns empty candidates

- **WHEN** the handler runs on `https://github.com/octocat/Hello-World/issues/42`
- **THEN** `TierResult.next_links == []`
