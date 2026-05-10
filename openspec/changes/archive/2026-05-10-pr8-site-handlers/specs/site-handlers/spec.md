## ADDED Requirements

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
